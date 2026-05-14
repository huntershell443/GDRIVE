from django.urls import path
from . import views

app_name = 'binary_analyzer'

urlpatterns = [
    path('',                              views.analyses_list,   name='list'),
    path('file/<int:file_id>/',           views.analysis_report, name='report'),
    path('file/<int:file_id>/status/',    views.analysis_status, name='status'),
    path('file/<int:file_id>/trigger/',   views.trigger_analysis, name='trigger'),
    path('file/<int:file_id>/recheck-vt/', views.recheck_virustotal, name='recheck_vt'),
    path('badges/',                       views.badges_for_files, name='badges'),
]
