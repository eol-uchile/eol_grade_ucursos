#!/bin/dash
pip install -e git+https://github.com/eol-uchile/uchileedxlogin@9c9b4ee047515026ce71cbd8aa1a457d2c3d4e5e#egg=uchileedxlogin
pip install -e /openedx/requirements/eol_grade_ucursos

cd /openedx/requirements/eol_grade_ucursos/gradeucursos
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/eol_grade_ucursos/gradeucursos

DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest tests.py
