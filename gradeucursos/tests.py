#!/usr/bin/env python
# -*- coding: utf-8 -*-
from mock import patch, Mock, MagicMock
from collections import namedtuple
from django.urls import reverse
from django.test import TestCase, Client
from django.test import Client
from django.conf import settings
from django.contrib.auth.models import User
from opaque_keys.edx.locator import CourseLocator
from student.tests.factories import CourseEnrollmentAllowedFactory, UserFactory, CourseEnrollmentFactory
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from student.roles import CourseInstructorRole, CourseStaffRole
from .views import GradeUcursosView, GradeUcursosExportView, task_get_data
from lms.djangoapps.grades.tests.utils import mock_get_score
from lms.djangoapps.grades.tests.base import GradeTestBase
from lms.djangoapps.grades.course_grade_factory import CourseGradeFactory
from common.djangoapps.student.tests.factories import CourseAccessRoleFactory
from lms.djangoapps.instructor_task.models import ReportStore
from collections import OrderedDict, defaultdict
import json

class TestGradeUcursosView(GradeTestBase):
    def setUp(self):
        super(TestGradeUcursosView, self).setUp()
        self.grade_factory = CourseGradeFactory()
        with patch('student.models.cc.User.save'):
            # staff user
            self.client_instructor = Client()
            self.client_student = Client()
            self.client_anonymous = Client()
            self.user_instructor = UserFactory(
                username='instructor',
                password='12345',
                email='instructor@edx.org',
                is_staff=True)
            role = CourseInstructorRole(self.course.id)
            role.add_users(self.user_instructor)
            self.client_instructor.login(
                username='instructor', password='12345')
            self.student = UserFactory(
                username='student',
                password='test',
                email='student@edx.org')
            self.student_2 = UserFactory(
                username='student_2',
                password='test',
                email='student2@edx.org')
            # Enroll the student in the course
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course.id, mode='honor')
            CourseEnrollmentFactory(
                user=self.student_2, course_id=self.course.id, mode='honor')
            self.client_student.login(
                username='student', password='test')
            # Create and Enroll data researcher user
            self.data_researcher_user = UserFactory(
                username='data_researcher_user',
                password='test',
                email='data.researcher@edx.org')
            CourseEnrollmentFactory(
                user=self.data_researcher_user,
                course_id=self.course.id, mode='audit')
            CourseAccessRoleFactory(
                course_id=self.course.id,
                user=self.data_researcher_user,
                role='data_researcher',
                org=self.course.id.org
            )
            self.client_data_researcher = Client()
            self.assertTrue(self.client_data_researcher.login(username='data_researcher_user', password='test'))
    
    def test_get_user_grade(self):
        """
            Verify method get_user_grade() work correctly
        """
        with mock_get_score(1, 4):
            self.grade_factory.update(self.student, self.course, force_update_subsections=True)
        with mock_get_score(1, 4):
            percent = GradeUcursosView().get_user_grade(self.student, self.course.id, 'gradeucursos_total', False)
            self.assertEqual(percent, {'Prom':0.25})

    def test_round_half_up(self):
        """
            Verify method grade_percent_scaled() work correctly
        """
        grades = [1,1.1,1.1,1.2,1.2,1.3,1.3,1.4,1.4,1.5,1.5,1.6,1.6,1.7,1.7,1.8,1.8,1.9,1.9,2,2,2.1,2.1,2.2,2.2,2.3,2.3,2.4,2.4,2.5,2.5,2.6,2.6,2.7,2.7,2.8,2.8,2.9,2.9,3,3,3.1,3.1,3.2,3.2,3.3,3.3,3.4,3.4,3.5,3.5,3.6,3.6,3.7,3.7,3.8,3.8,3.9,3.9,4,4,4.1,4.2,4.2,4.3,4.4,4.5,4.5,4.6,4.7,4.8,4.8,4.9,5,5.1,5.1,5.2,5.3,5.4,5.4,5.5,5.6,5.7,5.7,5.8,5.9,6,6,6.1,6.2,6.3,6.3,6.4,6.5,6.6,6.6,6.7,6.8,6.9,6.9,7]
        for i in range(101):
            self.assertEqual(GradeUcursosView().grade_percent_scaled(i/100,0.6), grades[i])

    def test_gradeucursos_get(self):
        """
            Test gradeucursos view
        """
        response = self.client_instructor.get(reverse('gradeucursos-export:data'))
        request = response.request
        self.assertEqual(response.status_code, 405)

    def test_gradeucursos_post(self):
        """
            Test gradeucursos post normal process
        """
        with mock_get_score(1, 2):
            self.grade_factory.update(self.student, self.course, force_update_subsections=True)
            self.grade_factory.update(self.student_2, self.course, force_update_subsections=True)
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id),
            'instructor_tab': 'false',
            'assig_type': 'gradeucursos_total',
            'is_resumen': 'false'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['status'] , 'Generating')
        response2 = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        r2 = json.loads(response2._container[0].decode())
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(r2['status'] , 'Generated')
        report_grade, _ = GradeUcursosView().get_grade_report(post_data['curso'], post_data['grade_type'], 'gradeucursos_total', False)
        self.assertTrue(report_grade is not None)
        self.assertEqual(len(report_grade), 2)
        self.assertEqual(report_grade[0], ['9472337-K', self.student.username, '', {'Prom':4.0}])
        obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(self.student_2.username)
        self.assertEqual(report_grade[1], ['', self.student_2.username, obs, {'Prom':4.0}])

    def test_gradeucursos_post_data_researcher(self):
        """
            Test gradeucursos post normal process with data researcher role
        """
        with mock_get_score(1, 2):
            self.grade_factory.update(self.student, self.course, force_update_subsections=True)
            self.grade_factory.update(self.student_2, self.course, force_update_subsections=True)
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_data_researcher.post(reverse('gradeucursos-export:data'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['status'] , 'Generating')
        response2 = self.client_data_researcher.post(reverse('gradeucursos-export:data'), post_data)
        r2 = json.loads(response2._container[0].decode())
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(r2['status'] , 'Generated')
        report_grade, _ = GradeUcursosView().get_grade_report(post_data['curso'], post_data['grade_type'], 'gradeucursos_total', False)
        self.assertTrue(report_grade is not None)
        self.assertEqual(len(report_grade), 2)
        self.assertEqual(report_grade[0], ['9472337-K', self.student.username, '', {'Prom':4.0}])
        obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(self.student_2.username)
        self.assertEqual(report_grade[1], ['', self.student_2.username, obs, {'Prom':4.0}])

    def test_gradeucursos_post_from_instructor_tab(self):
        """
            Test gradeucursos post from instructor tab normal process
        """
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        task_input = {
            'grade_type': 'seven_scale',
            'course_id': str(self.course.id),
            'instructor_tab': True,
            'assig_type': 'gradeucursos_total',
            'is_resumen': False
        }
        with patch('lms.djangoapps.instructor_task.tasks_helper.runner._get_current_task'):
            result = task_get_data(
                None, None, self.course.id,
                task_input, 'EOL_GRADE_UCURSOS'
            )
        report_store = ReportStore.from_config(config_name='GRADES_DOWNLOAD')
        report_csv_filename = report_store.links_for(self.course.id)[0][0]
        report_path = report_store.path_to(self.course.id, report_csv_filename)
        self.assertTrue('_notas_estudiantes_' in report_csv_filename)
        self.assertTrue('_notas_estudiantes_' in report_path)

    def test_gradeucursos_post_from_instructor_tab_assig_type(self):
        """
            Test gradeucursos post from instructor tab normal process with assignament
        """
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        task_input = {
            'grade_type': 'seven_scale',
            'course_id': str(self.course.id),
            'instructor_tab': True,
            'assig_type': 'Homework',
            'is_resumen': False
        }
        with patch('lms.djangoapps.instructor_task.tasks_helper.runner._get_current_task'):
            result = task_get_data(
                None, None, self.course.id,
                task_input, 'EOL_GRADE_UCURSOS'
            )
        report_store = ReportStore.from_config(config_name='GRADES_DOWNLOAD')
        report_csv_filename = report_store.links_for(self.course.id)[0][0]
        report_path = report_store.path_to(self.course.id, report_csv_filename)
        self.assertTrue('_notas_estudiantes_' in report_csv_filename)
        self.assertTrue('_notas_estudiantes_' in report_path)

    def test_gradeucursos_post_from_instructor_tab_assig_type_data(self):
        """
            Test gradeucursos post from instructor tab normal process with assignament
        """
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id),
            'instructor_tab': 'true',
            'assig_type': 'Homework',
            'is_resumen': 'false'
        }
        #grade cutoff 50%
        report_grade, _ = GradeUcursosView().get_grade_report(post_data['curso'], post_data['grade_type'], 'gradeucursos_total', False)
        self.assertTrue(report_grade is not None)
        self.assertEqual(len(report_grade), 2)
        self.assertEqual(report_grade[0], ['9472337-K', self.student.username, '', {'Prom':1.0}])
        obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(self.student_2.username)
        self.assertEqual(report_grade[1], ['', self.student_2.username, obs, {'Prom':1.0}])

    def test_gradeucursos_post_from_instructor_tab_is_resumen(self):
        """
            Test gradeucursos post from instructor tab normal process with is_resumen params
        """
        with mock_get_score(1, 2):
            self.grade_factory.update(self.student, self.course, force_update_subsections=True)
            self.grade_factory.update(self.student_2, self.course, force_update_subsections=True)
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        task_input = {
            'grade_type': 'seven_scale',
            'course_id': str(self.course.id),
            'instructor_tab': True,
            'assig_type': 'Homework',
            'is_resumen': True
        }
        with patch('lms.djangoapps.instructor_task.tasks_helper.runner._get_current_task'):
            result = task_get_data(
                None, None, self.course.id,
                task_input, 'EOL_GRADE_UCURSOS'
            )
        report_store = ReportStore.from_config(config_name='GRADES_DOWNLOAD')
        report_csv_filename = report_store.links_for(self.course.id)[0][0]
        report_path = report_store.path_to(self.course.id, report_csv_filename)
        self.assertTrue('_notas_estudiantes_' in report_csv_filename)
        self.assertTrue('_notas_estudiantes_' in report_path)

    def test_gradeucursos_post_from_instructor_tab_is_resumen_data(self):
        """
            Test gradeucursos post from instructor tab normal process with is_resumen params
        """
        with mock_get_score(1, 2):
            self.grade_factory.update(self.student, self.course, force_update_subsections=True)
            self.grade_factory.update(self.student_2, self.course, force_update_subsections=True)
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        report_grade, headers = GradeUcursosView().get_grade_report(post_data['curso'], post_data['grade_type'], 'gradeucursos_total', True)
        self.assertTrue(report_grade is not None)
        self.assertEqual(len(report_grade), 2)
        result = OrderedDict([('Homework', 50.0), ('NoCredit', 0.0), ('Prom', 4.0)])
        self.assertEqual(report_grade[0], ['9472337-K', self.student.username, '', result])
        obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(self.student_2.username)
        self.assertEqual(report_grade[1], ['', self.student_2.username, obs, result])

    def test_gradeucursos_post_from_instructor_tab_wrong_assig_type(self):
        """
            Test gradeucursos post from instructor tab wrong assignament type
        """
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id),
            'instructor_tab': 'true',
            'assig_type': 'asdasdsads',
            'is_resumen': 'false'
        }
        response = self.client_data_researcher.post(reverse('gradeucursos-export:data'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['status'] , 'Error')
        self.assertTrue(r['error_assig_type'])

    def test_gradeucursos_post_not_logged(self):
        """
            Test gradeucursos get when user is not logged
        """
        response = self.client_anonymous.post(reverse('gradeucursos-export:data'))
        self.assertEqual(response.status_code, 404)

    def test_gradeucursos_post_course_no_exists(self):
        """
            Test gradeucursos post when course_id no exists
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': 'course-v1:eol+test+2021'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['error_curso'])

    def test_gradeucursos_post_wrong_course_id(self):
        """
            Test gradeucursos post when course_id is not CourseKey
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': 'asdasd'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['error_curso'])

    def test_gradeucursos_post_empty_course_id(self):
        """
            Test gradeucursos post when course_id is empty
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': ''
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['empty_course'])

    def test_gradeucursos_post_wrong_scale_grade(self):
        """
            Test gradeucursos post when dont exists grade_type in GRADE_TYPE_LIST
        """
        post_data = {
            'grade_type': 'wrong_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['error_grade_type'])

    def test_gradeucursos_post_wrong_is_resumen(self):
        """
            Test gradeucursos post when is_resumen is not boolean type
        """
        post_data = {
            'grade_type': 'wrong_scale',
            'curso': str(self.course.id),
            'is_resumen': 'hello world!'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['error_is_resumen'])

    def test_gradeucursos_post_user_dont_have_permission(self):
        """
            Test gradeucursos post when user dont have permission to export 
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_student.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['user_permission'])

    @patch('gradeucursos.views.GradeUcursosView.get_grade_cutoff')
    def test_gradeucursos_post_grade_cutoff_not_defined(self, grade):
        """
            Test gradeucursos post when grade cutoff is not defined
        """
        grade.return_value = None
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        self.assertEqual(response.status_code, 200)
        r = json.loads(response._container[0].decode())
        self.assertTrue(r['error_grade_cutoff'])

    def test_gradeucursos_post_uchileedxlogin_not_installed(self):
        """
            Test gradeucursos post when uchileedxlogin is not installed
        """
        from unittest.case import SkipTest
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        try:
            from uchileedxlogin.models import EdxLoginUser
            self.skipTest("this test check if validate_data function verify EdxLoginUser model")
        except ImportError:
            response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
            self.assertEqual(response.status_code, 200)
            r = json.loads(response._container[0].decode())
            self.assertTrue(r['error_model'])

    @patch('gradeucursos.views.GradeUcursosView.get_grade_cutoff')
    def test_gradeucurso_post_grade_cutoff_not_defined_in_report(self, grade):
        """
            Test gradeucursos post when grade cutoff is not defined
        """
        grade.side_effect = [0.5, None, 0.5]
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id),
            'instructor_tab': 'false',
            'assig_type': 'gradeucursos_total',
            'is_resumen': 'false'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        response_export = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['status'] , 'Generating')
        r2 = json.loads(response_export._container[0].decode())
        self.assertTrue(r2['report_error'])

    @patch('gradeucursos.views.GradeUcursosView.get_grade_cutoff')
    def test_gradeucursos_post_from_instructor_tab_grade_cutoff_not_defined_in_report(self, grade):
        """
            Test gradeucursos post from instructor tab when grade cutoff is not defined
        """
        grade.return_value = None
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        task_input = {
            'grade_type': 'seven_scale',
            'course_id': str(self.course.id),
            'instructor_tab': True,
            'assig_type': 'gradeucursos_total',
            'is_resumen': False
        }
        with patch('lms.djangoapps.instructor_task.tasks_helper.runner._get_current_task'):
            result = task_get_data(
                None, None, self.course.id,
                task_input, 'EOL_GRADE_UCURSOS'
            )
        report_store = ReportStore.from_config(config_name='GRADES_DOWNLOAD')
        report_csv_filename = report_store.links_for(self.course.id)[0][0]
        report_path = report_store.path_to(self.course.id, report_csv_filename)
        self.assertTrue('_Error_notas_estudiantes_' in report_csv_filename)
        self.assertTrue('_Error_notas_estudiantes_' in report_path)

class TestGradeUcursosExportView(GradeTestBase):
    def setUp(self):
        super(TestGradeUcursosExportView, self).setUp()
        self.grade_factory = CourseGradeFactory()
        with patch('student.models.cc.User.save'):
            # staff user
            self.client_instructor = Client()
            self.client_student = Client()
            self.client_anonymous = Client()
            self.user_instructor = UserFactory(
                username='instructor',
                password='12345',
                email='instructor@edx.org',
                is_staff=True)
            role = CourseInstructorRole(self.course.id)
            role.add_users(self.user_instructor)
            self.client_instructor.login(
                username='instructor', password='12345')
            self.student = UserFactory(
                username='student',
                password='test',
                email='student@edx.org')
            self.student_2 = UserFactory(
                username='student_2',
                password='test',
                email='student2@edx.org')
            # Enroll the student in the course
            CourseEnrollmentFactory(
                user=self.student, course_id=self.course.id, mode='honor')
            CourseEnrollmentFactory(
                user=self.student_2, course_id=self.course.id, mode='honor')
            self.client_student.login(
                username='student', password='test')

    def test_gradeucursosexport_get(self):
        """
            Test gradeucursosexport view
        """
        response = self.client_instructor.get(reverse('gradeucursos-export:export'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/gradeucursos/export')

    def test_gradeucursosexport_get_not_logged(self):
        """
            Test gradeucursosexport get when user is not logged
        """
        response = self.client_anonymous.post(reverse('gradeucursos-export:export'))
        self.assertEqual(response.status_code, 404)
    
    def test_gradeucursosexport_post(self):
        """
            Test gradeucursosexport post normal process
        """
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['status'] , 'Generating')
        response_export = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response_export._headers['content-type'], ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))

    def test_gradeucursosexport_post_course_no_exists(self):
        """
            Test gradeucursosexport post when course_id no exists
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': 'course-v1:eol+test+2021'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_curso"' in response._container[0].decode())

    def test_gradeucursosexport_post_wrong_course_id(self):
        """
            Test gradeucursosexport post when course_id is not CourseKey
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': 'asdasd'
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_curso"' in response._container[0].decode())

    def test_gradeucursosexport_post_empty_course_id(self):
        """
            Test gradeucursosexport post when course_id is empty
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': ''
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="empty_course"' in response._container[0].decode())

    def test_gradeucursosexport_post_wrong_scale_grade(self):
        """
            Test gradeucursosexport post when dont exists grade_type in GRADE_TYPE_LIST
        """
        post_data = {
            'grade_type': 'wrong_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_grade_type"' in response._container[0].decode())

    def test_gradeucursosexport_post_user_dont_have_permission(self):
        """
            Test gradeucursosexport post when user dont have permission to export 
        """
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_student.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="user_permission"' in response._container[0].decode())

    @patch('gradeucursos.views.GradeUcursosView.get_grade_cutoff')
    def test_gradeucursosexport_post_grade_cutoff_not_defined(self, grade):
        """
            Test gradeucursosexport post when grade cutoff is not defined
        """
        grade.return_value = None
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        response = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id="error_grade_cutoff"' in response._container[0].decode())

    def test_gradeucursosexport_post_uchileedxlogin_not_installed(self):
        """
            Test gradeucursosexport post when uchileedxlogin is not installed
        """
        from unittest.case import SkipTest
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        try:
            from uchileedxlogin.models import EdxLoginUser
            self.skipTest("this test check if validate_data function verify EdxLoginUser model")
        except ImportError:
            response = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue('id="error_model"' in response._container[0].decode())
    
    @patch('gradeucursos.views.GradeUcursosView.get_grade_cutoff')
    def test_gradeucursosexport_post_grade_cutoff_not_defined_in_report(self, grade):
        """
            Test gradeucursosexport post when grade cutoff is not defined
        """
        grade.side_effect = [0.5, None, 0.5]
        try:
            from unittest.case import SkipTest
            from uchileedxlogin.models import EdxLoginUser
            EdxLoginUser.objects.create(user=self.student, run='09472337K')
        except ImportError:
            self.skipTest("import error uchileedxlogin")
        post_data = {
            'grade_type': 'seven_scale',
            'curso': str(self.course.id)
        }
        #grade cutoff 50%
        response = self.client_instructor.post(reverse('gradeucursos-export:data'), post_data)
        r = json.loads(response._container[0].decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(r['status'] , 'Generating')
        response_export = self.client_instructor.post(reverse('gradeucursos-export:export'), post_data)
        self.assertEqual(response_export.status_code, 200)
        self.assertTrue('id="report_error"' in response_export._container[0].decode())