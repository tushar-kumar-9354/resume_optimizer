from django.db import models
from django.contrib.auth.models import User

class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name


# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name

class Challenge(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    description = models.TextField()
    reason = models.TextField(blank=True, null=True)
    mcq_questions = models.JSONField(default=list)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="PENDING")
    
    # Optional fields - we'll add them properly
    fill_in_blanks = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.skill.name} - {self.user.username}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    resume = models.FileField(upload_to='resumes/', unique=False)
    resume_text = models.TextField(blank=True, null=True)  # ADD THIS FIELD
    skills = models.ManyToManyField(Skill, blank=True)  # Make optional
    ats_score = models.IntegerField(null=True, blank=True)
    top_skills = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # Optional: track creation
    updated_at = models.DateTimeField(auto_now=True)  # Optional: track updates
    
    def __str__(self):
        return self.user.username
    
    
from django.db import models
from django.contrib.auth.models import User
# core/models.py

from django.db import models
from django.contrib.auth.models import User

class ProjectStep(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('DONE', 'Done'),
        ('FAILED', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    project_title = models.CharField(max_length=200)
    week = models.IntegerField()
    step_description = models.TextField()
    code_output = models.TextField(blank=True)
    code_explanation = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"{self.project_title} - Week {self.week}"
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Activity(models.Model):
    ACTIVITY_TYPES = [
        ('CHALLENGE_COMPLETE', 'Challenge Completed'),
        ('PROJECT_START', 'Project Started'),
        ('SKILL_IMPROVE', 'Skill Improved'),
        ('PROJECT_UPDATE', 'Project Updated'),
        ('RESUME_UPLOAD', 'Resume Uploaded'),
        ('RESUME_UPLOAD_ATTEMPT', 'Duplicate Resume Attempt'),
        ('RESUME_UPLOAD_ERROR', 'Resume Upload Error'),
        ('RESUME_ANALYSIS', 'Resume Analyzed'),
        ('CHALLENGES_GENERATED', 'Challenges Generated'),
        ('NO_CHALLENGES', 'No Challenges Generated'),
        ('CHALLENGE_GENERATION_ERROR', 'Challenge Generation Error')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    title = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = "Activities"
    
    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()}: {self.title}"
    
    def get_icon_path(self):
        icon_map = {
            'RESUME_UPLOAD': 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
            'RESUME_ANALYSIS': 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4',
            'CHALLENGES_GENERATED': 'M13 10V3L4 14h7v7l9-11h-7z',
            'NO_CHALLENGES': 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
            'CHALLENGE_COMPLETE': 'M5 13l4 4L19 7',
            'PROJECT_START': 'M12 4v16m8-8H4',
            'SKILL_IMPROVE': 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
            'PROJECT_UPDATE': 'M3 10h2a1 1 0 011 1v7a1 1 0 01-1 1H3m0-9V5a2 2 0 012-2h14a2 2 0 012 2v5m-2 4h2a1 1 0 011 1v7a1 1 0 01-1 1h-2',
            'RESUME_UPLOAD_ATTEMPT': 'M12 16v-8m0 0l-4 4m4-4l4 4',
            'RESUME_UPLOAD_ERROR': 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
            'CHALLENGE_GENERATION_ERROR': 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
        }
        return icon_map.get(self.activity_type, 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z')
    
    def get_time_ago(self):
        """Returns human-readable time difference"""
        diff = timezone.now() - self.timestamp
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        if diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        if diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        return "just now"