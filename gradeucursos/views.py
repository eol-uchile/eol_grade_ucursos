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
logger = logging.getLogger(__name__)

GRADE_TYPE_LIST = ['seven_scale', 'hundred_scale', 'percent_scale']
class GradeUcursosView(View):
    """
        Export all student grade in .xlsx format
    """
    def get(self, request):
        if not request.user.is_anonymous:
            return render(request, 'gradeucursos/data.html')
        else:
            logger.error("GradeUCursos - User is Anonymous")
        raise Http404()

    def post(self, request):
        if not request.user.is_anonymous:
            context = {'curso': request.POST.get('curso', ""),
                        'grade_type': request.POST.get("grade_type", "")
                        }
            context = self.validate_data(request.user, context)
            if len(context) == 2:
                report_grade = self.get_grade_report(context['curso'], context['grade_type'])
                if report_grade is None:
                    logger.error("GradeUCursos - Error to Generate report_grade, user: {}, context: {}".format(request.user.id, context))
                    context['report_error'] = True
                    return render(request, 'gradeucursos/data.html', context)
                return self.generate_report(report_grade)

            else:
                return render(request, 'gradeucursos/data.html', context)
        else:
            logger.error("GradeUCursos - User is Anonymous")
        raise Http404()

    def validate_data(self, user, context):
        # valida curso
        if context['curso'] == "":
            logger.error("GradeUCursos - Empty course, user: {}".format(user.id))
            context['empty_course'] = True
       
        # valida si existe el curso
        else:
            if not self.validate_course(context['curso']):
                logger.error("GradeUCursos - Couse dont exists, user: {}, course_id: {}".format(user.id, context['curso']))
                context['error_curso'] = True

            elif not self.user_have_permission(user, context['curso']):
                logger.error("GradeUCursos - user dont have permission in the course, course: {}, user: {}".format(context['curso'], user))
                context['user_permission'] = True

        # si el grade_type es incorrecto
        if not context['grade_type'] in GRADE_TYPE_LIST:
            context['error_grade_type'] = True
            logger.error("GradeUCursos - Wrong grade_type, user: {}, grade_type: {}".format(user.id, context['grade_type']))

        return context
    
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

    def generate_report(self, report_grade):
        """
            Generate Excel File
        """
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response['Content-Disposition'] = "attachment; filename=notas_estudiantes.xlsx"

        workbook = xlsxwriter.Workbook(response, {'in_memory': True})
        worksheet = workbook.add_worksheet()
        # Add a bold format to use to highlight cells.
        bold = workbook.add_format({'bold': True})
        # Write some data headers.
        worksheet.write('A1', 'RUT', bold)
        worksheet.write('B1', 'Observaciones', bold)
        worksheet.write('C1', 'Nota', bold)
        row = 1
        for data in report_grade:
            worksheet.write(row, 0, data[0])
            worksheet.write(row, 1, data[1])
            worksheet.write(row, 2, data[2])
            row += 1
        workbook.close()

        return response

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