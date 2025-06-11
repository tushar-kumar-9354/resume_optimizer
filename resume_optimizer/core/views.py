# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from .forms import ResumeUploadForm
from .models import UserProfile, Challenge
from .utils import extract_resume_text, generate_challenges_from_feedback, analyze_resume

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('upload_resume')
    else:
        form = UserCreationForm()
    return render(request, 'core/register.html', {'form': form})

@login_required
def upload_resume(request):
    if request.method == 'POST':
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            user_profile, created = UserProfile.objects.get_or_create(user=request.user)

            new_resume = form.cleaned_data['resume']
            if user_profile.resume and user_profile.resume.name == new_resume.name:
                messages.info(request, "You've already uploaded this resume.")
                print("already  uploaded same resume....")
                return redirect('challenge_list')

            user_profile.resume = new_resume
            user_profile.save()

            uploaded_file = request.FILES['resume']
            uploaded_file.seek(0)

            try:
                resume_text = extract_resume_text(uploaded_file)
            except Exception as e:
                messages.error(request, f"Error reading resume PDF: {str(e)}")
                print("Error reading resume PDF:", e)
                return redirect('upload_resume')

            feedback = analyze_resume(resume_text)
            print("🧠 AI Feedback:", feedback)

            try:
                generated_count = generate_challenges_from_feedback(request.user, feedback)
                if generated_count:
                    messages.success(request, f'{generated_count} new challenges generated based on your resume!')
                else:
                    messages.info(request, 'No new challenges generated.')
            except Exception as e:
                messages.error(request, f"Error generating challenges: {str(e)}")
                return redirect('/challenges/')

            return redirect('/challenges/')
    else:
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
    import json
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
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def week_code_view(request):
    code_output = ""
    project_title = ""
    step_description = ""
    previous_steps = []

    if request.method == "POST":
        step_description = request.POST.get("step_description", "")
        project_title = request.POST.get("project_title", "")
        skills = request.session.get("skills", [])
        plan = request.session.get("plan", [])
        previous_steps = request.session.get("previous_steps", [])

        # Append current step to history (if not already present)
        if step_description not in previous_steps:
            previous_steps.append(step_description)
            request.session["previous_steps"] = previous_steps

        code_output = generate_code_for_step(project_title, step_description, skills, previous_steps)

    return render(request, "core/week_code.html", {
        "project_title": project_title,
        "step_description": step_description,
        "code_output": code_output
    })
