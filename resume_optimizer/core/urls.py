# core/urls.py
from django.urls import path
from . import views
from .views import project_timeline_view , project_dashboard_view, regenerate_step_code

urlpatterns = [
    path('upload/', views.upload_resume, name='upload_resume'),
    path('challenges/', views.challenge_list, name='challenge_list'),
    path('challenges/<int:pk>/', views.challenge_detail, name='challenge_detail'),
    path("resume/", views.generate_project_ideas_view, name="resume"),
    path('week_code/', views.week_code_view, name='week_code'),
    path("project_timeline/", project_timeline_view, name="project_timeline"),
    path("dashboard/", project_dashboard_view, name="project_dashboard"),
    path("regenerate/<int:step_id>/", regenerate_step_code, name="regenerate_step"),

]
