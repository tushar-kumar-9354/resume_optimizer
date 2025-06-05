from django import forms
from .models import UserProfile

class ResumeUploadForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['resume']
