# core/urls.py
from django.urls import path
from . import views
from .views import project_timeline_view

urlpatterns = [
    path('upload/', views.upload_resume, name='upload_resume'),
    path('challenges/', views.challenge_list, name='challenge_list'),
    path('challenges/<int:pk>/', views.challenge_detail, name='challenge_detail'),
    path("resume/", views.generate_project_ideas_view, name="resume"),
    path('week_code/', views.week_code_view, name='week_code'),
    path("project_timeline/", project_timeline_view, name="project_timeline"),

]
