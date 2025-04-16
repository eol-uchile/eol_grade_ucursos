#!/usr/bin/env python
# -- coding: utf-8 --
# Python Standard Libraries
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import partial
from io import BytesIO
from time import time
import json
import logging

# Installed packages (via pip)
from celery import task
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import FieldError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import ugettext_noop
from django.views.generic.base import View
from pytz import UTC
import xlsxwriter

# Edx dependencies
from common.djangoapps.util.file import course_filename_prefix_generator
from courseware.access import has_access
from courseware.courses import get_course_by_id, get_course_with_access
from lms.djangoapps.grades.course_grade_factory import CourseGradeFactory
from lms.djangoapps.instructor import permissions
from lms.djangoapps.instructor_task.api_helper import AlreadyRunningError, submit_task
from lms.djangoapps.instructor_task.models import ReportStore
from lms.djangoapps.instructor_task.tasks_base import BaseInstructorTask
from lms.djangoapps.instructor_task.tasks_helper.runner import run_main_task, TaskProgress
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

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
    assig_type = task_input["assig_type"]
    instructor_tab = task_input['instructor_tab']
    is_resumen = task_input['is_resumen']
    start_time = time()
    task_progress = TaskProgress(
        action_name,
        1,
        start_time)

    report_grade, headers = GradeUcursosView().get_grade_report(task_input['course_id'], grade_type, assig_type, is_resumen)
    if instructor_tab:
        GradeUcursosView().generate_report_instructor_tab_temporary(report_grade, course_key, is_resumen, assig_type, headers)
        current_step = {'step': 'Uploading Data Eol Grade UCursos'}
    else:
        data = {'report_grade': report_grade, 'state': ''}
        if report_grade is None:
            data['state'] = 'error'
            cache.set("eol_grade_ucursos-{}-{}-data".format(task_input["course_id"], grade_type), data, 60) #1 minute
            current_step = {'step': 'Error to uploading Data Eol Grade UCursos'}
        else:
            data['state'] = 'success'
            cache.set("eol_grade_ucursos-{}-{}-data".format(task_input["course_id"], grade_type), data, 300) #5 minute
            current_step = {'step': 'Uploading Data Eol Grade UCursos'}
    return task_progress.update_task_state(extra_meta=current_step)

def task_process_data(request, course_id, grade_type, assig_type='gradeucursos_total', instructor_tab=False, is_resumen=False):
    course_key = CourseKey.from_string(course_id)
    task_type = 'EOL_GRADE_UCURSOS'
    task_class = process_data
    task_input = {'course_id': course_id, 'grade_type': grade_type, 'assig_type': assig_type, 'instructor_tab':instructor_tab, 'is_resumen':is_resumen}
    task_key = "{}_{}_{}_{}".format(course_id, grade_type, assig_type, 'is_resumen' if is_resumen else '')

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

            else:
                # valida permisos de usuario
                if not self.user_have_permission(user, data['curso']):
                    logger.error("GradeUCursos - user dont have permission in the course, course: {}, user: {}".format(data['curso'], user))
                    error['user_permission'] = True
                course_key = CourseKey.from_string(data['curso'])
                grade_cutoff = self.get_grade_cutoff(course_key)
                # valida grade_cutoff del curso
                if grade_cutoff is None:
                    logger.error("GradeUCursos - grade_cutoff is not defined, course: {}, user: {}".format(data['curso'], user))
                    error['error_grade_cutoff'] = True
                # si el assig_type es incorrecto
                #if data['instructor_tab']:
                #    assignament_types = self._get_assignment_types(course_key)
                #    if data['assig_type'] not in assignament_types and data['assig_type'] != 'gradeucursos_total':
                #        logger.error("GradeUCursos - Wrong assignament_types, course: {}, user: {}, assig_type: {}, assignament_types".format(data['curso'], user, data['assig_type'], assignament_types))
                #        error['error_assig_type'] = True
        # si el grade_type es incorrecto
        if not data['grade_type'] in GRADE_TYPE_LIST:
            error['error_grade_type'] = True
            logger.error("GradeUCursos - Wrong grade_type, user: {}, grade_type: {}".format(user.id, data['grade_type']))
        
        # si is_resumen no es boolean
        #if type(data['is_resumen']) is not bool:
        #    error['error_is_resumen'] = True
        #    logger.error("GradeUCursos - Wrong is_resumen, user: {}, is_resumen: {}".format(user.id, data['is_resumen']))

        try:
            from uchileedxlogin.models import EdxLoginUser
        except ImportError:
            logger.error("GradeUCursos - UchileEdxLogin not installed, course: {}, user: {}".format(data['curso'], user))
            error['error_model'] = True
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
            Verify if the user is instructor or staff course or data researcher
        """
        try:
            course = get_course_with_access(user, "load", course_key)
            data_researcher_access = user.has_perm(permissions.CAN_RESEARCH, course_key)
            return bool(has_access(user, 'instructor', course)) or bool(has_access(user, 'staff', course)) or data_researcher_access
        except Exception as e:
            logger.error('GradeUCursos - Error in is_instructor_or_staff({}, {}), Exception {}'.format(user, str(course_key), str(e)))
            return False

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

    def _get_assignment_types(self, course_key):
        """
        Helper function that returns a serialized dict of assignment types
        for the given course.
        """
        course = get_course_by_id(course_key)
        serialized_grading_policies = {}
        for grader, assignment_type, weight in course.grader.subgraders:
            serialized_grading_policies[assignment_type] = {
                'type': assignment_type,
                'short_label': grader.short_label,
                'min_count': grader.min_count,
                'drop_count': grader.drop_count,
                'weight': weight,
            }
        return serialized_grading_policies

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
                'grade_type': request.POST.get("grade_type", ""),
                'assig_type': 'gradeucursos_total',
                'is_resumen': True
            }
            try:
                data['instructor_tab'] = json.loads(request.POST.get('instructor_tab', 'false'))
            except json.decoder.JSONDecodeError:
                logger.error("GradeUCursos - Wrong instructor_tab, user: {}, instructor_tab: {}".format( request.user, request.POST.get('instructor_tab', 'false')))
                data['instructor_tab'] = False

            #try:
            #    data['is_resumen'] = json.loads(request.POST.get('is_resumen', 'false'))
            #except json.decoder.JSONDecodeError:
            #    logger.error("GradeUCursos - Wrong is_resumen, user: {}, is_resumen: {}".format( request.user, request.POST.get("is_resumen", 'false')))
            #    data['is_resumen'] = 'wrong'

            data_error = self.validate_data(request.user, data)
            if len(data_error) == 0:
                if data['instructor_tab']:
                    return self.get_data_report_instructor_tab(request, data['curso'], data['grade_type'], data['assig_type'], data['is_resumen'])
                else:
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
        report = cache.get("eol_grade_ucursos-{}-{}-data".format(course_id, grade_type))
        if report is None:
            try:
                task = task_process_data(request, course_id, grade_type)
                success_status = 'Generating'
                return JsonResponse({"status": success_status, "task_id": task.task_id})
            except AlreadyRunningError:
                logger.error("GradeUCursos - Task Already Running Error, user: {}, course_id: {}".format(request.user, course_id))
                return JsonResponse({'status': 'AlreadyRunningError'})
        elif report['state'] == 'error':
            return JsonResponse({'report_error': True, 'status': 'Error'})
        return JsonResponse({'status': 'Generated'})

    def get_data_report_instructor_tab(self, request, course_id, grade_type, assig_type, is_resumen):
        """
            generate report with task_process for instructor tab
        """
        try:
            task = task_process_data(request, course_id, grade_type, assig_type=assig_type, instructor_tab=True, is_resumen=is_resumen)
            success_status = 'Generating'
            return JsonResponse({"status": success_status, "task_id": task.task_id})
        except AlreadyRunningError:
            logger.error("GradeUCursos - Task Already Running Error, user: {}, course_id: {}".format(request.user, course_id))
            return JsonResponse({'status': 'AlreadyRunningError'})

    def get_grade_report(self, course_id, scale, assig_type, is_resumen):
        """
            Generate list of all student grade 
            report_grade = [['rut_student_1','obs',0.6],['rut_student_2','obs',0.6],...]
        """
        course_key = CourseKey.from_string(course_id)
        grade_cutoff = self.get_grade_cutoff(course_key)
        report_grade = []
        headers = []
        i=0
        if grade_cutoff is None:
            logger.error('GradeUCursos - grade_cutoff is not defined')
            return None, None
        try:
            enrolled_students = User.objects.filter(
                courseenrollment__course_id=course_key,
                courseenrollment__mode='honor',
                courseenrollment__is_active=1
            ).order_by('username').values('id', 'username', 'edxloginuser__run')
        except FieldError:
            logger.error('GradeUCursos - UchileEdxLogin not installed')
            return None, None
        for user in enrolled_students:
            grade = self.get_user_scale(User.objects.get(id=user['id']), course_key, scale, assig_type, grade_cutoff, is_resumen)
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
            report_grade.append([user_rut, user['username'], obs, grade])
            if len(headers) == 0 and len(grade) != 0:
                headers = [x for x in grade]
            i += 1
        return report_grade, headers

    def generate_report_instructor_tab(self, report_grade, course_key, is_resumen, assig_type, headers):
        """
            Generate Excel File
        """
        report_store = ReportStore.from_config('GRADES_DOWNLOAD')
        output = BytesIO()
        xlsx_name = 'notas_estudiantes'
        workbook = xlsxwriter.Workbook(output)
    
        worksheet = workbook.add_worksheet()
        # Add a bold format to use to highlight cells.
        bold = workbook.add_format({'bold': True})
        # Write some data headers.
        worksheet.write('A1', 'RUT', bold)
        worksheet.write('B1', 'Observaciones', bold)
        worksheet.write(0,0,'RUT', bold)
        worksheet.write(0,1,'Username', bold)
        worksheet.write(0,2,'Observaciones', bold)
        if report_grade is None:
            xlsx_name = 'Error_notas_estudiantes'
        else:
            if is_resumen:
                i = 3
                if assig_type == 'gradeucursos_total':
                    percents = self._get_assignment_types(course_key)
                    for h in headers:
                        if h == 'Prom':
                            worksheet.write(0,i,'{}'.format(h), bold)
                        else:
                            worksheet.write(0,i,'P{} {}% {}'.format(i-2, percents[h]['weight']*100, h), bold)
                        i += 1
                else:
                    for h in headers:
                        if h == 'Prom':
                            worksheet.write(0,i,'{}'.format(h), bold)
                        else:
                            worksheet.write(0,i,'P{} {}'.format(i-2,h), bold)
                        i += 1
            else:
                worksheet.write(0,3,'Nota', bold)
            worksheet.set_column('A:A', 11)  # Column A width set to 11.
            worksheet.set_column('B:B', 15)  # Column B width set to 15.
            worksheet.set_column('C:C', 27)  # Column C width set to 27.
            row = 1
            for data in report_grade:
                worksheet.write(row, 0, data[0])
                worksheet.write(row, 1, data[1])
                worksheet.write(row, 2, data[2])
                i = 3
                for grade in headers:
                    worksheet.write(row,i,data[3][grade])
                    i += 1
                row += 1

        workbook.close()
        start_date = datetime.now(UTC)
        report_name = u"{course_prefix}_{xlsx_name}_{timestamp_str}.xlsx".format(
            course_prefix=course_filename_prefix_generator(course_key),
            xlsx_name=xlsx_name,
            timestamp_str=start_date.strftime("%Y-%m-%d-%H%M%S")
        )
        # Get the output bytes for creating a django file
        output = output.getvalue()
        # Generate the data file
        data_file = ContentFile(output)
        report_store.store(course_key, report_name, data_file)

    def generate_report_instructor_tab_temporary(self, report_grade, course_key, is_resumen, assig_type, headers):
        """
            Generate Excel File with assignament grade in observations column
        """
        report_store = ReportStore.from_config('GRADES_DOWNLOAD')
        output = BytesIO()
        xlsx_name = 'notas_estudiantes'
        workbook = xlsxwriter.Workbook(output)
    
        worksheet = workbook.add_worksheet()
        # Add a bold format to use to highlight cells.
        bold = workbook.add_format({'bold': True})
        # Write some data headers.
        worksheet.write('A1', 'RUT', bold)
        worksheet.write('B1', 'Observaciones', bold)
        worksheet.write(0,0,'RUT', bold)
        worksheet.write(0,1,'Username', bold)
        worksheet.write(0,2,'Observaciones', bold)
        worksheet.write(0,3,'Nota', bold)
        worksheet.set_column('A:A', 11)  # Column A width set to 11.
        worksheet.set_column('B:B', 15)  # Column B width set to 15.
        worksheet.set_column('C:C', 27)  # Column C width set to 27.
        cell_format = workbook.add_format()
        cell_format.set_text_wrap()
        if report_grade is None:
            xlsx_name = 'Error_notas_estudiantes'
        else:
            percents = self._get_assignment_types(course_key)
            row = 1
            for data in report_grade:
                worksheet.write(row, 0, data[0])
                worksheet.write(row, 1, data[1])
                obs = data[2]
                if obs != '':
                    obs = obs + '\n'
                height = 15
                j = 1
                for h in headers:
                    if h != 'Prom':
                       obs += 'P{} {}% {}: {}%\n'.format(j, percents[h]['weight']*100, h, data[3][h])
                       height += 15
                    j += 1
                worksheet.write(row, 2, obs, cell_format)
                worksheet.write(row,3,data[3]['Prom'])
                worksheet.set_row(row, height)
                row += 1

        workbook.close()
        start_date = datetime.now(UTC)
        report_name = u"{course_prefix}_{xlsx_name}_{timestamp_str}.xlsx".format(
            course_prefix=course_filename_prefix_generator(course_key),
            xlsx_name=xlsx_name,
            timestamp_str=start_date.strftime("%Y-%m-%d-%H%M%S")
        )
        # Get the output bytes for creating a django file
        output = output.getvalue()
        # Generate the data file
        data_file = ContentFile(output)
        report_store.store(course_key, report_name, data_file)

    def get_user_scale(self, user, course_key, scale, assig_type, grade_cutoff, is_resumen):
        """
            Convert the percentage rating based on the scale
        """
        dict_percent = self.get_user_grade(user, course_key, assig_type, is_resumen)
        for key in dict_percent:
            if key != 'Prom':
                dict_percent[key] = int(self.grade_percent_ucursos_scaled(dict_percent[key], grade_cutoff)*100)
            else:
                if scale == 'seven_scale':
                    dict_percent[key] = self.grade_percent_scaled(dict_percent[key], grade_cutoff)
                elif scale == 'hundred_scale':
                    dict_percent[key] = int(self.grade_percent_ucursos_scaled(dict_percent[key], grade_cutoff)*100)
                elif scale == 'percent_scale':
                    dict_percent[key] = self.grade_percent_ucursos_scaled(dict_percent[key], grade_cutoff)
        return dict_percent

    def get_user_grade(self, user, course_key, assig_type, is_resumen):
        """
            Get user grade
            return {'Prom': %} or {'Prom': %, 'assig 1': %, 'assig 2': %, 'assig 3': % ...}
        """
        response = CourseGradeFactory().read(user, course_key=course_key)
        notas = OrderedDict()
        if response is not None:
            if is_resumen:
                if assig_type == 'gradeucursos_total':
                    for assig in response.summary['section_breakdown']:
                        if 'prominent' in assig and assig['prominent']:
                            notas[assig['category']] = assig['percent']
                    notas['Prom'] = response.percent
                    return notas
                else:
                    for assig in response.summary['section_breakdown']:
                        if assig['category'] == assig_type and 'prominent' in assig and assig['prominent']:
                            notas['Prom'] = assig['percent']
                            break
                        elif assig['category'] == assig_type:
                            notas[assig['label']] = assig['percent']
                    return notas
            else:
                if assig_type == 'gradeucursos_total':
                    notas['Prom'] = response.percent
                    return notas
                else:
                    for assig in response.summary['section_breakdown']:
                        if assig['category'] == assig_type and 'prominent' in assig and assig['prominent']:
                            notas['Prom'] = assig['percent']
                            break
                    return notas
        return notas

    def grade_percent_scaled(self, grade_percent, grade_cutoff):
        """
            EOL: Scale grade percent by grade cutoff. Grade between 1.0 - 7.0
        """
        if grade_percent == 0.:
            return 1.
        if grade_percent < grade_cutoff:
            return self.round_half_up((Decimal('3') / Decimal(str(grade_cutoff)) * Decimal(str(grade_percent)) + Decimal('1')))
        return self.round_half_up(Decimal('3') / Decimal(str(1. - grade_cutoff)) * Decimal(str(grade_percent)) + (Decimal('7') - (Decimal('3') / Decimal(str(1. - grade_cutoff)))))

    def round_half_up(self, number):
        return float(Decimal(str(float(number))).quantize(Decimal('0.1'), ROUND_HALF_UP))

    def grade_percent_ucursos_scaled(self, grade_percent, grade_cutoff):
        """
            EOL: Scale grade percent by grade cutoff to grade percent by grade cutoff = 50%
        """
        grade = self.grade_percent_scaled(grade_percent, grade_cutoff)
        return float(Decimal(str((1/6)*(grade-1))).quantize(Decimal('0.01'), ROUND_HALF_UP))

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
                'data_url': reverse('gradeucursos-export:data'),
                'instructor_tab': False,
                'is_resumen': False
            }
            data_error = self.validate_data(request.user, context)
            context.update(data_error)
            if len(data_error) == 0:
                data_report = cache.get("eol_grade_ucursos-{}-{}-data".format(context['curso'], context['grade_type']))
                if data_report is None:
                    logger.error("GradeUCursos - The data has not been generated yet, user: {}, data: {}".format(request.user, context))
                    context['report_error'] = True
                    return render(request, 'gradeucursos/data.html', context)
                else:
                    if data_report['state'] == 'success':
                        return self.generate_report(data_report['report_grade'], context['curso'])
                    else:
                        logger.error("GradeUCursos - Error to generate report or grade_cutoff is not defined, user: {}, data: {}".format(request.user, context))
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
            if 'Prom' in data[2]:
                worksheet.write(row, 2, data[2]['Prom'])
            else:
                worksheet.write(row, 2, '')
            row += 1
        workbook.close()

        return response
