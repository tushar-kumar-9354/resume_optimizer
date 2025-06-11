from django.db import models
from django.contrib.auth.models import User

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
    mcq_questions = models.JSONField(default=list)  # Contains all MCQ data including answers
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="PENDING")

    def __str__(self):
        return f"{self.skill.name} - {self.user.username}"
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    resume = models.FileField(upload_to='resumes/', unique=False)  # Allows duplicates
    skills = models.ManyToManyField(Skill)
    
    def __str__(self):
        return self.user.username
from django.db import models
from django.contrib.auth.models import User

class ProjectStep(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    project_title = models.CharField(max_length=255)
    week = models.IntegerField()
    step_description = models.TextField()
    code_output = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "project_title", "week")  # Prevent duplicates

    def __str__(self):
        return f"{self.project_title} - Week {self.week}"
