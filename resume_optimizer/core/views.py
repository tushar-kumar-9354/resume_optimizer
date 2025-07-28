# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from urllib3 import request
from .forms import ResumeUploadForm
from .models import UserProfile, Challenge
from .utils import extract_resume_text, generate_challenges_from_feedback, analyze_resume, log_activity
from django.db.models import Q

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'core/register.html', {'form': form})
from django.shortcuts import redirect, render
from django.contrib import messages
from .forms import ResumeUploadForm
from .models import UserProfile, Activity
from .utils import extract_resume_text, analyze_resume, extract_skills
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ResumeUploadForm
from .models import UserProfile, Activity
from .utils import extract_resume_text, generate_challenges_from_feedback
import re
import google.generativeai as genai  # Gemini SDK

# Set your Gemini API Key (ideally from env variable)
GEMINI_API_KEY = "AIzaSyChEo4-UNUDHLS51mZUayZleaQFyg1uziw"

def get_ats_score_from_gemini(resume_text):
    prompt = f"""
You are an ATS (Applicant Tracking System) simulator.

Given the following resume text, give an overall ATS score (out of 100) based on clarity, keyword presence, formatting, and technical relevance. Also extract top 5 technical skills clearly.

Format your response like this:
ATS Score: <number>
Skills: <comma-separated list of top 5 skills>

Resume:
\"\"\"{resume_text}\"\"\"
"""
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        content = response.text.strip()
        print("Gemini ATS Analysis Response:", content)

        # Parse response
        ats_score = 0
        skills = []

        match = re.search(r'ATS Score:\s*(\d+)', content)
        if match:
            ats_score = int(match.group(1))

        skills_match = re.search(r'Skills:\s*(.*)', content)
        if skills_match:
            skills = [s.strip() for s in skills_match.group(1).split(',')[:5]]

        return ats_score, skills

    except Exception as e:
        print("Gemini ATS error:", str(e))
        return 0, []  # fallback



def classify_skill_level_with_gemini(skill, project_descriptions):
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""
You are given a list of project step descriptions:

{project_descriptions}

From this list:
1. Extract the technical skills or technologies used (e.g., Python, Django, PostgreSQL, Generative AI, etc.).
2. For each extracted skill:
    - Analyze how frequently it is mentioned or used.
    - Analyze the complexity of its usage based on the project context.
3. Based on this analysis, assign a skill level for each skill:
    - Beginner: Basic or few usages.
    - Intermediate: Moderate frequency or mid-level usage.
    - Advanced: High frequency and complex or critical usage in projects.

Return your output in this format (as JSON):
{{
  "Python": "Intermediate",
  "Django": "Beginner",
  ...
}}
"""
    print("Gemini Skill Classification Prompt:", prompt)
    response = model.generate_content(prompt)
    return response.text.strip()

def upload_resume(request):
    if request.method == 'POST':
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                user_profile, created = UserProfile.objects.get_or_create(user=request.user)
                new_resume = form.cleaned_data['resume']

                # Save resume file
                user_profile.resume = new_resume
                user_profile.save()

                # Extract resume text
                uploaded_file = request.FILES['resume']
                uploaded_file.seek(0)
                resume_text = extract_resume_text(uploaded_file)
                user_profile.resume_text = resume_text[:100000]
                user_profile.save()

                # Log upload
                Activity.objects.create(
                    user=request.user,
                    activity_type='RESUME_UPLOAD',
                    title='Uploaded new resume',
                    details=f"Filename: {new_resume.name[:200]}"
                )

                # 🎯 GEMINI: Get ATS score and top skills
                ats_score, top_skills = get_ats_score_from_gemini(resume_text)
                user_profile.ats_score = ats_score
                user_profile.top_skills = ', '.join(top_skills)
                user_profile.save()

                Activity.objects.create(
                    user=request.user,
                    activity_type='RESUME_ANALYSIS',
                    title='Gemini resume analysis completed',
                    details=f"Score: {ats_score}, Skills: {', '.join(top_skills)}"
                )

                # Optionally generate challenges
                feedback = analyze_resume(resume_text)
                generated_count = generate_challenges_from_feedback(request.user, feedback)

                print(f"Generated {generated_count} challenges from resume analysis.")
                if generated_count == 0:
                    Activity.objects.create(
                        user=request.user,
                        activity_type='CHALLENGE_GENERATION_ERROR',
                        title='No challenges generated from resume analysis',
                        details="Resume analysis shows all skills are already demonstrated in your projects."
                    )

                if generated_count > 0:
                    Activity.objects.create(
                        user=request.user,
                        activity_type='CHALLENGES_GENERATED',
                        title='Generated new challenges',
                        details=f"Count: {generated_count}"
                    )


                return redirect('/challenges/')

            except Exception as e:
                Activity.objects.create(
                    user=request.user,
                    activity_type='RESUME_UPLOAD_ERROR',
                    title='Resume processing failed',
                    details=f"Error: {str(e)}"
                )
                messages.error(request, f"Error processing resume: {str(e)}")
                return redirect('upload_resume')

    form = ResumeUploadForm()
    return render(request, 'core/upload_resume.html', {'form': form})

@login_required
def challenge_list(request):
    challenges = Challenge.objects.filter(user=request.user)
    return render(request, 'core/challenges_list.html', {'challenges': challenges})
# core/views.py (updated challenge_detail function)
@login_required
def challenge_detail(request, pk):
    challenge = get_object_or_404(Challenge, pk=pk)

    if request.method == 'POST':
        score = 0
        total = len(challenge.mcq_questions)
        for i, mcq in enumerate(challenge.mcq_questions):
            selected = request.POST.get(f'mcq_{i}')
            if selected == mcq['answer']:
                score += 1
        
        percentage = (score / total) * 100 if total > 0 else 0
        challenge.status = "PASSED" if percentage >= 70 else "FAILED"
        challenge.save()
        return redirect('challenge_list')

    return render(request, 'core/challenge_detail.html', {
        'challenge': challenge,
        'mcqs': challenge.mcq_questions,
       
    })
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from .utils import (
    extract_resume_text,
    extract_skills,
    generate_projects_based_on_skills,
    generate_project_plan,
    generate_code_for_step
)

@csrf_exempt
def generate_project_ideas_view(request):
    skills, projects, plan, code_output = [], [], [], None

    if request.method == "POST":
        # === Resume Upload ===
        if request.FILES.get("resume"):
            resume_file = request.FILES["resume"]
            resume_text = extract_resume_text(resume_file)
            skills = extract_skills(resume_text)
            projects = generate_projects_based_on_skills(skills)

            request.session["skills"] = skills
            request.session["projects"] = projects
            request.session["plan"] = []

        # === Regenerate Projects ===
        elif request.POST.get("regenerate") == "1":
            skills = request.session.get("skills", [])
            projects = generate_projects_based_on_skills(skills)
            request.session["projects"] = projects

        # === Generate Plan for a Project ===
        elif request.POST.get("action") == "plan":
            project_title = request.POST.get("project_title")
            project_description = request.POST.get("project_description")
            skills = request.POST.get("skills").split(", ")
            plan = generate_project_plan(project_title, project_description, skills)

            request.session["plan"] = plan
            request.session["previous_steps"] = []
            request.session["current_project_title"] = project_title
            request.session["current_project_description"] = project_description

            projects = request.session.get("projects", [])
            skills = request.session.get("skills", [])

        # === Generate Code for a Specific Step ===
        elif request.POST.get("action") == "code":
            
            step_description = request.POST.get("step_description")
            skills = request.session.get("skills", [])
            plan = request.session.get("plan", [])
            projects = request.session.get("projects", [])
            project_title = request.POST.get("project_title", request.session.get("current_project_title", ""))

            code_output = generate_code_for_step(project_title, step_description, skills)

    else:
        skills = request.session.get("skills", [])
        projects = request.session.get("projects", [])
        plan = request.session.get("plan", [])
        

    return render(request, "core/resume.html", {
        "skills": skills,
        "projects": projects,
        "plan": plan,
        "code_output": code_output,
    })
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from core.models import ProjectStep
from core.utils import generate_code_for_step
import google.generativeai as genai

model = genai.GenerativeModel("models/gemini-2.5-flash")

@csrf_exempt
@login_required
def week_code_view(request):
    """
    Handles displaying the code for each project step and allows
    asking Gemini specific follow-up questions based on the generated code.
    """
    code_output = ""
    code_explanation = ""
    ai_response = ""
    project_title = ""
    step_description = ""
    previous_steps = request.session.get("previous_steps", [])

    if request.method == "POST":
        project_title = request.POST.get("project_title", "")
        step_description = request.POST.get("step_description", "")

        # ➤ Generate code for this step
        if request.POST.get("action") == "code":
            skills = request.session.get("skills", [])
            plan = request.session.get("plan", [])
            
            if step_description not in previous_steps:
                previous_steps.append(step_description)
                request.session["previous_steps"] = previous_steps

            full_response = generate_code_for_step(project_title, step_description, skills, previous_steps)

            if "```" in full_response:
                parts = full_response.split("```", 1)
                code_explanation = parts[0].strip()
                code_output = parts[1].strip()
            else:
                lines = full_response.splitlines()
                code_explanation = "\n".join(lines[:5])
                code_output = "\n".join(lines[5:])

            week_number = next((s["week"] for s in request.session.get("plan", [])
                                if s["task"] == step_description), 0)

            ProjectStep.objects.update_or_create(
                user=request.user,
                project_title=project_title,
                week=week_number,
                defaults={
                    "step_description": step_description,
                    "code_output": full_response,
                }
            )

        # ➤ AI Assistant follow-up prompt
        elif request.POST.get("action") == "ask_gemini":
            user_query = request.POST.get("user_query", "")
            full_response = request.session.get("code_output", "")
            prompt = f"""
You are a senior full-stack mentor with deep Django & React expertise.
Project: {project_title}
Task (Week Step): {step_description}

Here is the full code generated for this step:
{full_response}

User's Question:
{user_query}

INSTRUCTIONS:
• If the question refers to a specific file (e.g., utils.py), answer only about that file.
• Provide file-specific guidance (e.g., pip installs, code placement).
• Format response in bullet points or file-based sections.
• Answer clearly and professionally, step-by-step.
"""
            try:
                resp = model.generate_content(prompt)
                ai_response = resp.text.strip()
                print("Gemini AI Response:", ai_response)
            except Exception:
                ai_response = "⚠️ Gemini failed to respond – please try again."
    print("Gemini AI Response:", ai_response)
    return render(request, "core/week_code.html", {
        "project_title": project_title,
        "step_description": step_description,
        "code_explanation": code_explanation,
        "code_output": code_output,
        "ai_response": ai_response,
    })

from .models import ProjectStep
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
@login_required
def project_timeline_view(request):
    steps = ProjectStep.objects.filter(user=request.user).order_by('week')
    return render(request, "core/timeline.html", {"steps": steps})

# core/views.py

from django.utils.timezone import now
from datetime import timedelta
from .models import ProjectStep

@login_required
def project_dashboard_view(request):
    user = request.user
    project_title = request.session.get("current_project_title", "")

    steps = ProjectStep.objects.filter(user=user, project_title=project_title).order_by("week")

    completed_count = steps.filter(status='DONE').count()
    total_steps = steps.count()
    percent_complete = int((completed_count / total_steps) * 100) if total_steps else 0

    return render(request, "core/dashboard.html", {
        "steps": steps,
        "percent_complete": percent_complete,
    })
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import UserProfile, Challenge, ProjectStep
from .utils import extract_resume_text, analyze_resume, extract_skills
import re
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import UserProfile, ProjectStep, Challenge
from .utils import extract_skills  # still used for fallback classification
import re

@login_required
def dashboard_data(request):
    try:
        # 1. Get user profile
        user_profile = UserProfile.objects.filter(user=request.user).first()
        print(f"User Profile: {user_profile}")
        
        # 2. Get active projects
        project_steps = ProjectStep.objects.filter(
            user=request.user,
            status__in=['PENDING', 'IN_PROGRESS']
        ).order_by('project_title', '-week')
        print(f"Project Steps: (len={len(project_steps)})")

        projects = []
        seen_titles = set()
        for step in project_steps:
            if step.project_title not in seen_titles:
                projects.append({
                    'project_title': step.project_title,
                    'current_week': step.week
                })
                seen_titles.add(step.project_title)
        
        # 1. Count active projects
        active_project_titles = ProjectStep.objects.filter(
            user=request.user,
            status__in=['PENDING', 'IN_PROGRESS']
        ).values_list('project_title', flat=True).distinct()

        print(f"Active Projects: {active_project_titles}")
        # 3. Count completed challenges
        completed_challenges = Challenge.objects.filter(
            user=request.user,
            status='PASSED'
        ).count()

        print(f"Completed Challenges: {completed_challenges}")

        # 4. Boosted ATS Score
        ats_score = user_profile.ats_score if user_profile else 0
        print(f"ATS Score: {ats_score}")

                # 5. Skill Level Classification
        skill_aliases = {
            'Python': ['python'],
            'Generative AI': ['generative ai', 'llm', 'prompt engineering', 'gemini', 'chatgpt'],
            'Django': ['django', 'views', 'models', 'orm', 'template'],
            'PostgreSQL': ['postgresql', 'sql', 'database'],
            'Data Structures & Algorithms': ['dsa', 'data structure', 'linked list', 'binary tree', 'sorting'],
        }

        skills = []
        if user_profile and user_profile.top_skills:
            skill_names = [s.strip() for s in user_profile.top_skills.split(',') if s.strip()]

            for skill in skill_names[:5]:
                aliases = skill_aliases.get(skill, [skill])
                keyword_filter = Q()
                for alias in aliases:
                    keyword_filter |= Q(step_description__icontains=alias)

                matching_steps = ProjectStep.objects.filter(user=request.user).filter(keyword_filter)
                project_count = matching_steps.count()

                # Updated classification logic
                if project_count >= 4:
                    level = 'Advanced'
                elif project_count >= 2:
                    level = 'Intermediate'
                else:
                    level = 'Beginner'

                skills.append({
                    'name': skill,
                    'level': level,
                    'project_count': project_count,
                    'is_complex': project_count >= 2  # More granular
                })



        # Return response
        return JsonResponse({
            'projects': projects,
            'completed_challenges': completed_challenges,
            'ats_score': ats_score,
            'skills': skills,
            "active_projects": len(list(active_project_titles)),
        })

    except Exception as e:
        return JsonResponse({
            'error': f'Failed to load dashboard data: {str(e)}'
        }, status=500)

def regenerate_step_code(request, step_id):
    step = get_object_or_404(ProjectStep, id=step_id, user=request.user)
    skills = request.session.get("skills", [])
    previous_steps = request.session.get("previous_steps", [])

    new_code = generate_code_for_step(step.project_title, step.step_description, skills, previous_steps)
    if "```" in new_code:
        explanation, code = new_code.split("```", 1)
    else:
        explanation = new_code.splitlines()[0:3]
        code = "\n".join(new_code.splitlines()[3:])

    step.code_output = code.strip()
    step.code_explanation = explanation.strip()
    step.status = 'PENDING'
    step.save()

    return redirect("project_dashboard")

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from .models import ProjectStep
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from .models import ProjectStep

@login_required
def mark_step_done(request, step_id):
    """
    Marks a project step as DONE for the authenticated user.
    """
    if request.method == "POST":
        step = get_object_or_404(ProjectStep, id=step_id, user=request.user)
        step.status = "DONE"
        step.save()
        return redirect("project_dashboard")
    return redirect("project_dashboard")  # Handle non-POST requests gracefully

@login_required
def mark_step_pending(request, step_id):
    """
    Reverts a project step's status to PENDING for the authenticated user.
    """
    if request.method == "POST":
        step = get_object_or_404(ProjectStep, id=step_id, user=request.user)
        step.status = "PENDING"
        step.save()
        return redirect("project_dashboard")
    return redirect("project_dashboard")  # Handle non-POST requests gracefully

def index(request):
    """
    Renders the index page.
    """
    return render(request, 'core/index.html')

from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from .models import Activity
import json
# views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Activity

@login_required
def user_activities(request):
    activities = Activity.objects.filter(user=request.user).order_by('-timestamp')[:10]
    
    activity_data = []
    for activity in activities:
        details = activity.details
        if activity.activity_type == 'RESUME_ANALYSIS':
            details = "Resume analysis completed"
        elif activity.activity_type == 'CHALLENGES_GENERATED':
            details = f"Generated {activity.details.split('Count: ')[1]} challenges" if 'Count: ' in activity.details else "Generated new challenges"
        elif activity.activity_type == 'NO_CHALLENGES':
            details = "No new challenges generated from resume analysis"
        elif activity.activity_type == 'RESUME_UPLOAD_ATTEMPT':
            details = "Duplicate resume upload attempt detected"
        elif activity.activity_type == 'RESUME_UPLOAD_ERROR':
            details = "Error processing resume upload"
        elif activity.activity_type == 'CHALLENGE_GENERATION_ERROR':
            details = "Error generating challenges from resume analysis"
        elif activity.activity_type == 'PROJECT_START':
            details = "Project started based on resume analysis"
        elif activity.activity_type == 'SKILL_IMPROVE':
            details = "Skill improved based on resume analysis"
        elif activity.activity_type == 'PROJECT_UPDATE':
            details = "Project updated with new challenges or steps"
        
        activity_data.append({
            'title': activity.title,
            'details': details,
            'icon_path': activity.get_icon_path(),
            'time_ago': activity.get_time_ago(),
            'type': activity.activity_type,
        })
    
    return JsonResponse({'activities': activity_data})

@login_required
def test_user(request):
    return JsonResponse({
        'username': request.user.username,
        'email': request.user.email,
        'id': request.user.id
    })