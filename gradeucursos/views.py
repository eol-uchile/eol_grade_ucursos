#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.shortcuts import render
from django.views.generic.base import View
from opaque_keys.edx.keys import CourseKey, UsageKey
from django.http import Http404, HttpResponse, JsonResponse

from collections import OrderedDict, defaultdict
from django.core.exceptions import FieldError
from django.contrib.auth.models import User
import requests
import json
import six
import hashlib
import os
import io
import logging
from django.urls import reverse
from opaque_keys import InvalidKeyError
from courseware.courses import get_course_by_id, get_course_with_access
from courseware.access import has_access
import unicodecsv as csv
from django.core.exceptions import FieldError
from lms.djangoapps.grades.course_grade_factory import CourseGradeFactory
import xlsxwriter
from django.core.cache import cache
from celery import current_task, task
from lms.djangoapps.instructor_task.tasks_base import BaseInstructorTask
from lms.djangoapps.instructor_task.api_helper import submit_task
from functools import partial
from time import time
from lms.djangoapps.instructor_task.tasks_helper.runner import run_main_task, TaskProgress
from django.db import IntegrityError, transaction
from django.utils.translation import ugettext_noop
from lms.djangoapps.instructor_task.api_helper import AlreadyRunningError
logger = logging.getLogger(__name__)

GRADE_TYPE_LIST = ['seven_scale', 'hundred_scale', 'percent_scale']

@task(base=BaseInstructorTask, queue='edx.lms.core.low')
def process_data(entry_id, xmodule_instance_args):
    action_name = ugettext_noop('generated')
    task_fn = partial(task_get_data, xmodule_instance_args)

    return run_main_task(entry_id, task_fn, action_name)


def task_get_data(
        _xmodule_instance_args,
        _entry_id,
        course_id,
        task_input,
        action_name):
    course_key = course_id
    grade_type = task_input["grade_type"]

    start_time = time()
    task_progress = TaskProgress(
        action_name,
        1,
        start_time)

    report_grade = GradeUcursosView().get_grade_report(task_input['course_id'], task_input['grade_type'])
    data = {'report_grade': report_grade, 'state': ''}
    if report_grade is None:
        data['state'] = 'error'
        cache.set("eol_grade_ucursos-{}-{}-data".format(task_input["course_id"], task_input["grade_type"]), data, 60) #1 minute
        current_step = {'step': 'Error to uploading Data Eol Grade UCursos'}
    else:
        data['state'] = 'success'
        cache.set("eol_grade_ucursos-{}-{}-data".format(task_input["course_id"], task_input["grade_type"]), data, 300) #5 minute
        current_step = {'step': 'Uploading Data Eol Grade UCursos'}
    return task_progress.update_task_state(extra_meta=current_step)


def task_process_data(request, course_id, grade_type):
    course_key = CourseKey.from_string(course_id)
    task_type = 'EOL_GRADE_UCURSOS'
    task_class = process_data
    task_input = {'course_id': course_id, 'grade_type': grade_type}
    task_key = "{}_{}".format(course_id, grade_type)

    return submit_task(
        request,
        task_type,
        task_class,
        course_key,
        task_input,
        task_key)

class Content(object):
    def validate_data(self, user, data):
        error = {}
        # valida curso
        if data['curso'] == "":
            logger.error("GradeUCursos - Empty course, user: {}".format(user.id))
            error['empty_course'] = True
       
        # valida si existe el curso
        else:
            if not self.validate_course(data['curso']):
                logger.error("GradeUCursos - Course dont exists, user: {}, course_id: {}".format(user.id, data['curso']))
                error['error_curso'] = True

            elif not self.user_have_permission(user, data['curso']):
                logger.error("GradeUCursos - user dont have permission in the course, course: {}, user: {}".format(data['curso'], user))
                error['user_permission'] = True

        # si el grade_type es incorrecto
        if not data['grade_type'] in GRADE_TYPE_LIST:
            error['error_grade_type'] = True
            logger.error("GradeUCursos - Wrong grade_type, user: {}, grade_type: {}".format(user.id, data['grade_type']))

        return error
    
    def validate_course(self, id_curso):
        """
            Verify if course.id exists
        """
        from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
        try:
            aux = CourseKey.from_string(id_curso)
            return CourseOverview.objects.filter(id=aux).exists()
        except InvalidKeyError:
            return False

    def user_have_permission(self, user, course_id):
        """
            Verify if user is instructor, staff_course or superuser
        """
        course_key = CourseKey.from_string(course_id)
        return self.is_instructor_or_staff(user, course_key) or user.is_staff

    def is_instructor_or_staff(self, user, course_key):
        """
            Verify if the user is instructor or staff course
        """
        try:
            course = get_course_with_access(user, "load", course_key)
            return bool(has_access(user, 'instructor', course)) or bool(has_access(user, 'staff', course))
        except Exception as e:
            logger.error('GradeUCursos - Error in is_instructor_or_staff({}, {}), Exception {}'.format(user, str(course_key), str(e)))
            return False

class GradeUcursosView(View, Content):
    """
        Generate and save in cache a list of all student grade
        report_grade = [['rut_student_1','obs',0.6],['rut_student_2','obs',0.6],...]
    """
    @transaction.non_atomic_requests
    def dispatch(self, args, **kwargs):
        return super(GradeUcursosView, self).dispatch(args, **kwargs)

    def post(self, request):
        if not request.user.is_anonymous:
            data = {
                'curso': request.POST.get('curso', ""),
                'grade_type': request.POST.get("grade_type", "")
            }
            data_error = self.validate_data(request.user, data)
            if len(data_error) == 0:
                return self.get_data_report(request, data['curso'], data['grade_type'])
            else:
                data_error['status'] = 'Error'
                return JsonResponse(data_error)
        else:
            logger.error("GradeUCursos - User is Anonymous")
        raise Http404()

    def get_data_report(self, request, course_id, grade_type):
        """
            get data from cache or task
        """
        if cache.get("eol_grade_ucursos-{}-{}-data".format(course_id, grade_type)) is None:
            try:
                task = task_process_data(request, course_id, grade_type)
                success_status = 'Generating'
                return JsonResponse({"status": success_status, "task_id": task.task_id})
            except AlreadyRunningError:
                logger.error("GradeUCursos - Task Already Running Error, user: {}, course_id: {}".format(request.user, course_id))
                return JsonResponse({'status': 'AlreadyRunningError'})
        return JsonResponse({'status': 'Generated'})

    def get_grade_report(self, course_id, scale):
        """
            Generate list of all student grade 
            report_grade = [['rut_student_1','obs',0.6],['rut_student_2','obs',0.6],...]
        """
        course_key = CourseKey.from_string(course_id)
        grade_cutoff = self.get_grade_cutoff(course_key)
        report_grade = []
        i=0
        if grade_cutoff is None:
            logger.error('GradeUCursos - grade_cutoff is not defined')
            return None
        try:
            enrolled_students = User.objects.filter(
                courseenrollment__course_id=course_key,
                courseenrollment__mode='honor'
            ).order_by('username').values('id', 'username', 'edxloginuser__run')
        except FieldError:
            logger.error('GradeUCursos - UchileEdxLogin not installed')
            return None
        for user in enrolled_students:
            grade = self.get_user_scale(User.objects.get(id=user['id']), course_key, scale, grade_cutoff)
            user_rut = ''
            obs = ''
            if user['edxloginuser__run'] is not None:
                try:
                    aux_run = user['edxloginuser__run']
                    run = str(int(aux_run[:-1])) + '-' + aux_run[-1]
                    user_rut = run
                except ValueError:
                    user_rut = user['edxloginuser__run']
                    obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(user['username'])
            else:
                obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(user['username'])
            report_grade.append([user_rut, obs, grade])
            i += 1
        return report_grade

    def get_user_scale(self, user, course_key, scale, grade_cutoff):
        """
            Convert the percentage rating based on the scale
        """
        percent = self.get_user_grade(user, course_key)
        if percent != '':
            if scale == 'seven_scale':
                return self.grade_percent_scaled(percent, grade_cutoff)
            elif scale == 'hundred_scale':
                return percent * 100
            elif scale == 'percent_scale':
                return percent
        return ''

    def get_user_grade(self, user, course_key):
        """
            Get user grade
        """
        response = CourseGradeFactory().read(user, course_key=course_key)
        if response is not None:
            return response.percent
        return ''

    def get_grade_cutoff(self, course_key):
        """
            Get course grade_cutoffs
        """
        # Load the course and user objects
        try:
            course = get_course_by_id(course_key)
            grade_cutoff = min(course.grade_cutoffs.values())  # Get the min value
            return grade_cutoff
        # For any course or user exceptions, kick the user back to the "Invalid" screen
        except (InvalidKeyError, Http404) as exception:
            error_str = (
                u"Invalid cert: error finding course %s "
                u"Specific error: %s"
            )
            logger.error(error_str, str(course_key), str(exception))
            return None

    def grade_percent_scaled(self, grade_percent, grade_cutoff):
        """
            EOL: Scale grade percent by grade cutoff. Grade between 1.0 - 7.0
        """
        if grade_percent == 0.:
            return 1.
        if grade_percent < grade_cutoff:
            return round(10. * (3. / grade_cutoff * grade_percent + 1.)) / 10.
        return round((3. / (1. - grade_cutoff) * grade_percent + (7. - (3. / (1. - grade_cutoff)))) * 10.) / 10.

class GradeUcursosExportView(View, Content):
    """
        Export all student grade in .xlsx format
    """

    def get(self, request):
        if not request.user.is_anonymous:
            context = {
                'data_url': reverse('gradeucursos-export:data')
            }
            return render(request, 'gradeucursos/data.html', context)
        else:
            logger.error("GradeUCursos - User is Anonymous")
        raise Http404()

    def post(self, request):
        if not request.user.is_anonymous:
            context = {
                'curso': request.POST.get('curso', ""),
                'grade_type': request.POST.get("grade_type", ""),
                'data_url': reverse('gradeucursos-export:data')
            }
            data_error = self.validate_data(request.user, context)
            context.update(data_error)
            print(context)
            if len(data_error) == 0:
                data_report = cache.get("eol_grade_ucursos-{}-{}-data".format(context['curso'], context['grade_type']))
                if data_report is None:
                    logger.error("GradeUCursos - The data has not been generated yet, user: {}, data: {}".format(request.user, data))
                    context['report_error'] = True
                    return render(request, 'gradeucursos/data.html', context)
                else:
                    if data_report['state'] == 'success':
                        return self.generate_report(data_report['report_grade'], context['curso'])
                    else:
                        logger.error("GradeUCursos - Error to generate report or grade_cutoff is no defined, user: {}, data: {}".format(request.user, data))
                        context['report_error'] = True
                        return render(request, 'gradeucursos/data.html', context)
            else:
                return render(request, 'gradeucursos/data.html', context)
        else:
            logger.error("GradeUCursos - User is Anonymous")
        raise Http404()
    
    def generate_report(self, report_grade, course_id):
        """
            Generate Excel File
        """
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response['Content-Disposition'] = "attachment; filename=notas_estudiantes_{}.xlsx".format(course_id)

        workbook = xlsxwriter.Workbook(response, {'in_memory': True})
        worksheet = workbook.add_worksheet()
        # Add a bold format to use to highlight cells.
        bold = workbook.add_format({'bold': True})
        # Write some data headers.
        worksheet.write('A1', 'RUT', bold)
        worksheet.set_column('A:A', 11)  # Column A width set to 11.
        worksheet.write('B1', 'Observaciones', bold)
        worksheet.set_column('B:B', 15)  # Column B width set to 15.
        worksheet.write('C1', 'Nota', bold)
        row = 1
        for data in report_grade:
            worksheet.write(row, 0, data[0])
            worksheet.write(row, 1, data[1])
            worksheet.write(row, 2, data[2])
            row += 1
        workbook.close()

        return response
