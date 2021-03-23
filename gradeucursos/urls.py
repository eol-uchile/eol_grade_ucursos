from django.contrib import admin
from django.conf.urls import url
from django.contrib.admin.views.decorators import staff_member_required
from .views import *


urlpatterns = [
    url('data', GradeUcursosView.as_view(), name='data'),
    url('export', GradeUcursosExportView.as_view(), name='export'),
]