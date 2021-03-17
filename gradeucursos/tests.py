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
from .views import GradeUcursosView
from lms.djangoapps.grades.tests.utils import mock_get_score
from lms.djangoapps.grades.tests.base import GradeTestBase
from lms.djangoapps.grades.course_grade_factory import CourseGradeFactory
import json

class TestGradeUcursosViewView(GradeTestBase):
    def setUp(self):
        super(TestGradeUcursosViewView, self).setUp()
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
    
    def test_get_user_grade(self):
        """
            Verify method get_user_grade() work correctly
        """
        with mock_get_score(1, 4):
            self.grade_factory.update(self.student, self.course, force_update_subsections=True)
        with mock_get_score(1, 4):
            percent = GradeUcursosView().get_user_grade(self.student, self.course.id)            
            self.assertEqual(percent, 0.25)
    
    def test_gradeucursos_get(self):
        """
            Test gradeucursos view
        """
        response = self.client_instructor.get(reverse('gradeucursos-export:data'))
        request = response.request
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request['PATH_INFO'], '/gradeucursos/data')

    def test_gradeucursos_get_not_logged(self):
        """
            Test gradeucursos get when user is not logged
        """
        response = self.client_anonymous.get(reverse('gradeucursos-export:data'))
        request = response.request
        self.assertEqual(response.status_code, 404)

    @patch('gradeucursos.views.GradeUcursosView.get_user_grade')
    def test_gradeucursos_post(self, grade):
        """
            Test gradeucursos post normal process
        """
        grade.return_value = 0.5
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
        self.assertEqual(response.status_code, 200)
        report_grade = GradeUcursosView().get_grade_report(post_data['curso'], post_data['grade_type'])
        self.assertTrue(report_grade is not None)
        self.assertEqual(len(report_grade), 2)
        self.assertEqual(report_grade[0], ['9472337-K', '', 4.0])
        obs = 'Usuario {} no tiene rut asociado en la plataforma.'.format(self.student_2.username)
        self.assertEqual(report_grade[1], ['', obs, 4.0])

    def test_gradeucursos_post_not_logged(self):
        """
            Test gradeucursos get when user is not logged
        """
        response = self.client_anonymous.post(reverse('gradeucursos-export:data'))
        request = response.request
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
        self.assertTrue('id="error_curso"' in response._container[0].decode())

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
        self.assertTrue('id="error_curso"' in response._container[0].decode())

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
        self.assertTrue('id="empty_course"' in response._container[0].decode())

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
        self.assertTrue('id="error_grade_type"' in response._container[0].decode())

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
        self.assertTrue('id="user_permission"' in response._container[0].decode())