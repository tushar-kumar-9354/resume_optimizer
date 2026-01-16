# core/urls.py
from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    # Authentication URLs
    path('register/', views.register, name='register'),
    
    # Main Pages
    path('', views.index, name='index'),
    path('upload/', views.upload_resume, name='upload_resume'),
    
    # Challenge URLs
    path('challenges/', views.challenge_list, name='challenge_list'),
    path('challenges/<int:pk>/', views.challenge_detail, name='challenge_detail'),
    
    # Project URLs
    path('resume/', views.generate_project_ideas_view, name='resume'),
    path('week_code/', views.week_code_view, name='week_code'),
    path('project_timeline/', views.project_timeline_view, name='project_timeline'),
    path('dashboard/', views.project_dashboard_view, name='project_dashboard'),
    path('step/<int:step_id>/mark-done/', views.mark_step_done, name='mark_step_done'),
    path('regenerate/<int:step_id>/', views.regenerate_step_code, name='regenerate_step'),
    path('step/<int:step_id>/mark-pending/', views.mark_step_pending, name='mark_step_pending'),
    
    # API Endpoints
    path('api/user/activities/', views.user_activities, name='user_activities'),
    path('test-user/', views.test_user, name='test_user'),
    path('dashboard-data/', views.dashboard_data, name='dashboard_data'),
    
    # API Testing and Monitoring
    path('test-api-1/', views.test_api_key_1, name='test_api_1'),
    path('test-api-2/', views.test_api_key_2, name='test_api_2'),
    path('token-dashboard/', views.token_usage_dashboard, name='token_dashboard'),
    path('reset-tokens/', views.reset_token_counts, name='reset_tokens'),
    
    # Logout
    path('logout/', LogoutView.as_view(next_page='index'), name='logout'),
    path('debug-challenges/', views.debug_challenges, name='debug_challenges'),
]