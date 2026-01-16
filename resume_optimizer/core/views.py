# core/views.py
from datetime import time
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.admin.views.decorators import staff_member_required 
from django.contrib import messages
from .forms import ResumeUploadForm
from .models import UserProfile, Challenge, ProjectStep, Activity

from .utils import (
    extract_resume_text, generate_challenges_from_feedback, 
    analyze_resume, log_activity, extract_skills,
    generate_projects_based_on_skills, generate_project_plan,
    generate_code_for_step
)
import google.generativeai as genai
import re
import random
import time as time_module

# API Key Distribution Setup
GEMINI_API_KEY_1 = "AIzaSyB601FSMEQGYGn2BNl3bhmMXscX2qOPets"
GEMINI_API_KEY_2 = "AIzaSyCmFAQPwXjvy_CL8z9-tlxnLxaYG9fCudQ"

GEMINI_API_KEYS = [GEMINI_API_KEY_1, GEMINI_API_KEY_2]

# Token usage tracking
token_usage = {
    'total_tokens_used': 0,
    'total_requests': 0,
    'last_request_time': None,
    'requests_by_endpoint': {},
    'api_key_usage': {GEMINI_API_KEY_1[:20]: 0, GEMINI_API_KEY_2[:20]: 0}
}

def update_token_usage(endpoint, input_tokens, output_tokens, total_tokens, api_key):
    """Update token usage statistics"""
    global token_usage
    
    token_usage['total_tokens_used'] += total_tokens
    token_usage['total_requests'] += 1
    token_usage['last_request_time'] = time_module.time()
    
    if endpoint not in token_usage['requests_by_endpoint']:
        token_usage['requests_by_endpoint'][endpoint] = {
            'count': 0,
            'total_tokens': 0,
            'input_tokens': 0,
            'output_tokens': 0
        }
    
    token_usage['requests_by_endpoint'][endpoint]['count'] += 1
    token_usage['requests_by_endpoint'][endpoint]['total_tokens'] += total_tokens
    token_usage['requests_by_endpoint'][endpoint]['input_tokens'] += input_tokens
    token_usage['requests_by_endpoint'][endpoint]['output_tokens'] += output_tokens
    
    # Track API key usage
    key_prefix = api_key[:20] + "..."
    token_usage['api_key_usage'][key_prefix] = token_usage['api_key_usage'].get(key_prefix, 0) + total_tokens
    
    # Log token usage
    print(f"\n📊 TOKEN USAGE - {endpoint}:")
    print(f"   Input tokens: {input_tokens}")
    print(f"   Output tokens: {output_tokens}")
    print(f"   Total tokens: {total_tokens}")
    print(f"   API Key: {api_key[:20]}...")
    print(f"   Cumulative total: {token_usage['total_tokens_used']} tokens")
    
    return total_tokens

def get_token_usage_stats():
    """Get current token usage statistics"""
    global token_usage
    return {
        'total_tokens_used': token_usage['total_tokens_used'],
        'total_requests': token_usage['total_requests'],
        'last_request_time': token_usage['last_request_time'],
        'requests_by_endpoint': token_usage['requests_by_endpoint'],
        'api_key_usage': token_usage['api_key_usage'],
        'estimated_cost': token_usage['total_tokens_used'] * 0.00000025,
        'tokens_remaining_key1': 1000000 - token_usage['api_key_usage'].get(GEMINI_API_KEY_1[:20] + "...", 0),
        'tokens_remaining_key2': 1000000 - token_usage['api_key_usage'].get(GEMINI_API_KEY_2[:20] + "...", 0)
    }

def count_tokens_for_text(text):
    """Approximate token count for text"""
    return len(text) // 4

def get_balanced_api_key(endpoint_type):
    """Get API key based on endpoint type and load balancing"""
    # Simple round-robin or load-based selection
    key1_usage = token_usage['api_key_usage'].get(GEMINI_API_KEY_1[:20] + "...", 0)
    key2_usage = token_usage['api_key_usage'].get(GEMINI_API_KEY_2[:20] + "...", 0)
    
    # For heavy operations, use key with less usage
    if endpoint_type in ['code_generation', 'project_plan']:
        return GEMINI_API_KEY_2 if key2_usage < key1_usage else GEMINI_API_KEY_1
    # For lighter operations, use key 1
    elif endpoint_type in ['ats_analysis', 'skill_classification']:
        return GEMINI_API_KEY_1
    # Default: alternate
    else:
        return random.choice([GEMINI_API_KEY_1, GEMINI_API_KEY_2])

def get_gemini_model(api_key, model_name="gemma-3-1b-it"):
    """Get Gemini model with specified API key"""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)

# Registration
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

# Resume Upload and Analysis
@login_required
def upload_resume(request):
    if request.method == 'POST':
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Create or update user profile
                user_profile, created = UserProfile.objects.get_or_create(user=request.user)
                new_resume = form.cleaned_data['resume']
                user_profile.resume = new_resume
                
                # Extract text
                uploaded_file = request.FILES['resume']
                uploaded_file.seek(0)
                resume_text = extract_resume_text(uploaded_file)
                user_profile.resume_text = resume_text[:50000]
                user_profile.save()
                
                # Log activity
                Activity.objects.create(
                    user=request.user,
                    activity_type='RESUME_UPLOAD',
                    title='Uploaded new resume',
                    details=f"File: {new_resume.name[:100]}"
                )
                
                # Analyze with Gemini (Use Key 1)
                api_key = GEMINI_API_KEY_1
                ats_score, top_skills = get_ats_score_from_gemini(resume_text, api_key)
                user_profile.ats_score = ats_score
                user_profile.top_skills = ', '.join(top_skills[:5])
                user_profile.save()
                
                Activity.objects.create(
                    user=request.user,
                    activity_type='RESUME_ANALYSIS',
                    title='Resume analysis completed',
                    details=f"Score: {ats_score}, Skills: {', '.join(top_skills[:3])}"
                )
                
                # Generate challenges (Use Key 2)
                api_key = GEMINI_API_KEY_2
                feedback = analyze_resume(resume_text, api_key)
                generated_count = generate_challenges_from_feedback(request.user, feedback, api_key)
                
                if generated_count > 0:
                    Activity.objects.create(
                        user=request.user,
                        activity_type='CHALLENGES_GENERATED',
                        title='New challenges generated',
                        details=f"Count: {generated_count}"
                    )
                
                return redirect('challenge_list')
                
            except Exception as e:
                Activity.objects.create(
                    user=request.user,
                    activity_type='RESUME_UPLOAD_ERROR',
                    title='Processing failed',
                    details=f"Error: {str(e)[:200]}"
                )
                messages.error(request, f"Error: {str(e)[:100]}")
                return redirect('upload_resume')
    
    form = ResumeUploadForm()
    return render(request, 'core/upload_resume.html', {'form': form})

# Gemini ATS Analysis
def get_ats_score_from_gemini(resume_text, api_key):
    """ATS analysis with API key"""
    prompt = f"""
Analyze resume and provide:
1. ATS Score (0-100)
2. Top 5 skills

Resume: {resume_text[:3000]}

Format: Score: X, Skills: A, B, C, D, E
"""
    try:
        input_tokens = count_tokens_for_text(prompt)
        model = get_gemini_model(api_key, "gemma-3-1b-it")
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        output_tokens = count_tokens_for_text(content)
        total_tokens = input_tokens + output_tokens
        update_token_usage('ats_analysis', input_tokens, output_tokens, total_tokens, api_key)
        
        # Parse
        ats_score = 0
        skills = []
        
        score_match = re.search(r'Score:\s*(\d+)', content)
        if score_match:
            ats_score = int(score_match.group(1))
        
        skills_match = re.search(r'Skills:\s*(.*)', content)
        if skills_match:
            skills = [s.strip() for s in skills_match.group(1).split(',')[:5]]
        
        return ats_score, skills
        
    except Exception as e:
        print(f"Gemini ATS error: {e}")
        return 50, []  # Default fallback

# Skill Classification
def classify_skill_level(skill, project_descriptions, api_key):
    """Skill classification with API key"""
    prompt = f"""
Skill: {skill}
Projects: {project_descriptions[:1000]}
Level: Beginner/Intermediate/Advanced
"""
    try:
        input_tokens = count_tokens_for_text(prompt)
        model = get_gemini_model(api_key, "gemma-3-1b-it")
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        output_tokens = count_tokens_for_text(content)
        total_tokens = input_tokens + output_tokens
        update_token_usage('skill_classification', input_tokens, output_tokens, total_tokens, api_key)
        
        level = content.split(':')[-1].strip()
        return level if level in ['Beginner', 'Intermediate', 'Advanced'] else 'Beginner'
    except:
        return 'Beginner'

# Challenge Views
@login_required
def challenge_list(request):
    challenges = Challenge.objects.filter(user=request.user)
    return render(request, 'core/challenges_list.html', {'challenges': challenges})

@login_required
def challenge_detail(request, pk):
    challenge = get_object_or_404(Challenge, pk=pk, user=request.user)
    
    if request.method == 'POST':
        score = sum(1 for i, mcq in enumerate(challenge.mcq_questions) 
                   if request.POST.get(f'mcq_{i}') == mcq['answer'])
        percentage = (score / len(challenge.mcq_questions)) * 100 if challenge.mcq_questions else 0
        challenge.status = "PASSED" if percentage >= 70 else "FAILED"
        challenge.save()
        return redirect('challenge_list')
    
    return render(request, 'core/challenge_detail.html', {
        'challenge': challenge,
        'mcqs': challenge.mcq_questions,
    })

# Project Generation Views
@login_required
def generate_project_ideas_view(request):
    skills = request.session.get('skills', [])
    projects = request.session.get('projects', [])
    plan = request.session.get('plan', [])
    code_output = None
    
    if request.method == "POST":
        # Resume upload
        if request.FILES.get("resume"):
            resume_file = request.FILES["resume"]
            resume_text = extract_resume_text(resume_file)
            skills = extract_skills(resume_text)
            # Use Key 2 for project generation
            projects = generate_projects_based_on_skills(skills, GEMINI_API_KEY_2)
            
            request.session["skills"] = skills
            request.session["projects"] = projects
        
        # Regenerate projects
        elif request.POST.get("regenerate") == "1":
            skills = request.session.get("skills", [])
            projects = generate_projects_based_on_skills(skills, GEMINI_API_KEY_2)
            request.session["projects"] = projects
        
        # Generate plan
        elif request.POST.get("action") == "plan":
            project_title = request.POST.get("project_title")
            project_description = request.POST.get("project_description")
            skills = request.POST.get("skills", "").split(", ")
            # Use balanced API key for plan generation
            api_key = get_balanced_api_key('project_plan')
            plan = generate_project_plan(project_title, project_description, skills, api_key)
            
            request.session["plan"] = plan
            request.session["current_project"] = {
                "title": project_title,
                "description": project_description
            }
        
        # Generate code
        elif request.POST.get("action") == "code":
            step_desc = request.POST.get("step_description", "")
            skills = request.session.get("skills", [])
            project_title = request.session.get("current_project", {}).get("title", "")
            
            if step_desc:
                # Use balanced API key for code generation
                api_key = get_balanced_api_key('code_generation')
                code_output = generate_code_for_step(project_title, step_desc, skills, api_key)
    
    return render(request, "core/resume.html", {
        "skills": skills,
        "projects": projects,
        "plan": plan,
        "code_output": code_output,
    })

# Code Generation View
@login_required
def week_code_view(request):
    code_output = ""
    explanation = ""
    ai_response = ""
    
    if request.method == "POST":
        project_title = request.POST.get("project_title", "")
        step_description = request.POST.get("step_description", "")
        
        # Generate code
        if request.POST.get("action") == "code":
            skills = request.session.get("skills", [])
            # Use Key 2 for code generation (usually heavier)
            code_output = generate_code_for_step(project_title, step_description, skills, GEMINI_API_KEY_2)
            
            # Save to database
            if code_output:
                ProjectStep.objects.create(
                    user=request.user,
                    project_title=project_title,
                    step_description=step_description,
                    code_output=code_output[:10000],
                    status='PENDING'
                )
        
        # Ask Gemini
        elif request.POST.get("action") == "ask_gemini":
            user_query = request.POST.get("user_query", "")
            code_context = request.POST.get("code_context", "")
            
            prompt = f"""
Code Context: {code_context[:1000]}
Question: {user_query}
Answer briefly:
"""
            try:
                # Use Key 1 for Q&A (lighter)
                api_key = GEMINI_API_KEY_1
                input_tokens = count_tokens_for_text(prompt)
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemma-3-1b-it")
                response = model.generate_content(prompt)
                ai_response = response.text.strip()
                
                output_tokens = count_tokens_for_text(ai_response)
                total_tokens = input_tokens + output_tokens
                update_token_usage('ask_gemini', input_tokens, output_tokens, total_tokens, api_key)
                
            except:
                ai_response = "Gemini unavailable"
    
    return render(request, "core/week_code.html", {
        "code_output": code_output,
        "explanation": explanation,
        "ai_response": ai_response,
    })

# Project Management Views
@login_required
def project_timeline_view(request):
    steps = ProjectStep.objects.filter(user=request.user).order_by('week')
    return render(request, "core/timeline.html", {"steps": steps})

@login_required
def project_dashboard_view(request):
    steps = ProjectStep.objects.filter(user=request.user).order_by("week")
    completed = steps.filter(status='DONE').count()
    total = steps.count()
    percent = int((completed / total) * 100) if total else 0
    
    return render(request, "core/dashboard.html", {
        "steps": steps,
        "percent_complete": percent,
    })

# Dashboard Data API
@login_required
def dashboard_data(request):
    try:
        profile = UserProfile.objects.filter(user=request.user).first()
        
        # Active projects
        active_projects = ProjectStep.objects.filter(
            user=request.user,
            status__in=['PENDING', 'IN_PROGRESS']
        ).values('project_title').distinct().count()
        
        # Completed challenges
        completed_challenges = Challenge.objects.filter(
            user=request.user,
            status='PASSED'
        ).count()
        
        # Skills with levels
        skills = []
        if profile and profile.top_skills:
            skill_list = [s.strip() for s in profile.top_skills.split(',')[:5]]
            for skill in skill_list:
                steps_count = ProjectStep.objects.filter(
                    user=request.user,
                    step_description__icontains=skill.lower()
                ).count()
                
                if steps_count >= 3:
                    level = 'Advanced'
                elif steps_count >= 1:
                    level = 'Intermediate'
                else:
                    level = 'Beginner'
                
                skills.append({
                    'name': skill,
                    'level': level,
                    'project_count': steps_count
                })
        
        return JsonResponse({
            'active_projects': active_projects,
            'completed_challenges': completed_challenges,
            'ats_score': profile.ats_score if profile else 50,
            'skills': skills,
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)[:200]}, status=500)

# Step Management
@login_required
def regenerate_step_code(request, step_id):
    step = get_object_or_404(ProjectStep, id=step_id, user=request.user)
    skills = request.session.get("skills", [])
    
    # Use Key 2 for regeneration
    new_code = generate_code_for_step(
        step.project_title, 
        step.step_description, 
        skills,
        GEMINI_API_KEY_2
    )
    
    if new_code:
        step.code_output = new_code[:10000]
        step.status = 'PENDING'
        step.save()
    
    return redirect("project_dashboard")

@login_required
def mark_step_done(request, step_id):
    if request.method == "POST":
        step = get_object_or_404(ProjectStep, id=step_id, user=request.user)
        step.status = "DONE"
        step.save()
    return redirect("project_dashboard")

@login_required
def mark_step_pending(request, step_id):
    if request.method == "POST":
        step = get_object_or_404(ProjectStep, id=step_id, user=request.user)
        step.status = "PENDING"
        step.save()
    return redirect("project_dashboard")

# Home and Activities
def index(request):
    return render(request, 'core/index.html')

@login_required
def user_activities(request):
    activities = Activity.objects.filter(
        user=request.user
    ).order_by('-timestamp')[:10]
    
    activity_data = []
    for activity in activities:
        activity_data.append({
            'title': activity.title,
            'details': activity.details[:100],
            'time_ago': activity.get_time_ago(),
            'type': activity.activity_type,
        })
    
    return JsonResponse({'activities': activity_data})

# Test endpoint
@login_required
def test_user(request):
    return JsonResponse({
        'username': request.user.username,
        'email': request.user.email,
        'id': request.user.id
    })

# API Key Testing Views
def test_api_key_1(request):
    """Test API Key 1"""
    try:
        api_key = GEMINI_API_KEY_1
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemma-3-1b-it')
        
        test_prompt = "Say 'Hello from API Key 1' and tell me the time."
        input_tokens = count_tokens_for_text(test_prompt)
        
        response = model.generate_content(test_prompt)
        
        output_tokens = count_tokens_for_text(response.text)
        total_tokens = input_tokens + output_tokens
        
        update_token_usage('test_api_key_1', input_tokens, output_tokens, total_tokens, api_key)
        
        stats = get_token_usage_stats()
        
        return HttpResponse(f"""
        <h3>✅ Success! API Key 1 is working.</h3>
        <p><strong>Response:</strong> {response.text}</p>
        <hr>
        <h4>📊 Token Usage:</h4>
        <p>Input tokens: {input_tokens}</p>
        <p>Output tokens: {output_tokens}</p>
        <p>Total tokens: {total_tokens}</p>
        <hr>
        <h4>📈 Cumulative Usage for Key 1:</h4>
        <p>Total tokens used: {stats['api_key_usage'].get(api_key[:20] + '...', 0)}</p>
        <p>Tokens remaining: {stats['tokens_remaining_key1']:,}</p>
        <hr>
        <p><small>Using key: {api_key[:20]}...</small></p>
        """)
    except Exception as e:
        return HttpResponse(f"<h3>❌ Error!</h3><p>{str(e)}</p><p>Using key: {GEMINI_API_KEY_1[:20]}...</p>")

def test_api_key_2(request):
    """Test API Key 2"""
    try:
        api_key = GEMINI_API_KEY_2
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemma-3-1b-it')
        
        test_prompt = "Say 'Hello from API Key 2' and mention Python."
        input_tokens = count_tokens_for_text(test_prompt)
        
        response = model.generate_content(test_prompt)
        
        output_tokens = count_tokens_for_text(response.text)
        total_tokens = input_tokens + output_tokens
        
        update_token_usage('test_api_key_2', input_tokens, output_tokens, total_tokens, api_key)
        
        stats = get_token_usage_stats()
        
        return HttpResponse(f"""
        <h3>✅ Success! API Key 2 is working.</h3>
        <p><strong>Response:</strong> {response.text}</p>
        <hr>
        <h4>📊 Token Usage:</h4>
        <p>Input tokens: {input_tokens}</p>
        <p>Output tokens: {output_tokens}</p>
        <p>Total tokens: {total_tokens}</p>
        <hr>
        <h4>📈 Cumulative Usage for Key 2:</h4>
        <p>Total tokens used: {stats['api_key_usage'].get(api_key[:20] + '...', 0)}</p>
        <p>Tokens remaining: {stats['tokens_remaining_key2']:,}</p>
        <hr>
        <p><small>Using key: {api_key[:20]}...</small></p>
        """)
    except Exception as e:
        return HttpResponse(f"<h3>❌ Error!</h3><p>{str(e)}</p><p>Using key: {GEMINI_API_KEY_2[:20]}...</p>")

# Token Usage Dashboard
@login_required
def token_usage_dashboard(request):
    """Display token usage statistics"""
    stats = get_token_usage_stats()
    
    # Format for display
    formatted_stats = {
        'total_tokens_used': f"{stats['total_tokens_used']:,}",
        'total_requests': stats['total_requests'],
        'estimated_cost': f"${stats['estimated_cost']:.6f}",
        'last_request_time': time_module.ctime(stats['last_request_time']) if stats['last_request_time'] else 'Never',
        'tokens_remaining_key1': f"{stats['tokens_remaining_key1']:,}",
        'tokens_remaining_key2': f"{stats['tokens_remaining_key2']:,}"
    }
    
    # Prepare endpoint breakdown
    endpoint_breakdown = []
    for endpoint, data in stats['requests_by_endpoint'].items():
        endpoint_breakdown.append({
            'endpoint': endpoint,
            'count': data['count'],
            'total_tokens': f"{data['total_tokens']:,}",
            'avg_per_request': f"{data['total_tokens'] // data['count']:,}" if data['count'] > 0 else "0"
        })
    
    # API key usage breakdown
    api_key_breakdown = []
    for key_prefix, usage in stats['api_key_usage'].items():
        api_key_breakdown.append({
            'key': key_prefix,
            'tokens_used': f"{usage:,}",
            'percentage': f"{(usage / stats['total_tokens_used'] * 100):.1f}%" if stats['total_tokens_used'] > 0 else "0%"
        })
    
    return render(request, 'core/token_dashboard.html', {
        'stats': formatted_stats,
        'endpoint_breakdown': endpoint_breakdown,
        'api_key_breakdown': api_key_breakdown,
        'api_keys': {
            'key1': GEMINI_API_KEY_1[:15] + '...',
            'key2': GEMINI_API_KEY_2[:15] + '...'
        }
    })

# Fallback function for when API is unavailable
def get_fallback_explanation(code_snippet):
    """Provide basic explanations when Gemini API is unavailable"""
    return "The AI explanation service is currently unavailable. Here are some general tips for understanding Python code:\n\n1. Read the code line by line\n2. Look for variable names and their purposes\n3. Identify loops and conditional statements\n4. Check function definitions and calls\n5. Trace the flow of data through the code"

# Reset token counts (admin only)
@staff_member_required
def reset_token_counts(request):
    """Reset token usage counts"""
    global token_usage
    token_usage = {
        'total_tokens_used': 0,
        'total_requests': 0,
        'last_request_time': None,
        'requests_by_endpoint': {},
        'api_key_usage': {GEMINI_API_KEY_1[:20]: 0, GEMINI_API_KEY_2[:20]: 0}
    }
    messages.success(request, "Token usage statistics have been reset.")
    return redirect('token_usage_dashboard')

@login_required
def debug_challenges(request):
    """Debug view to see what's happening with challenges"""
    from .models import Challenge, Skill
    
    print(f"\n🔍 DEBUG: User: {request.user.username}")
    print(f"🔍 DEBUG: User ID: {request.user.id}")
    
    # List all skills
    skills = Skill.objects.all()
    print(f"🔍 DEBUG: Total skills in DB: {skills.count()}")
    for skill in skills:
        print(f"  - Skill: {skill.name} (ID: {skill.id})")
    
    # List all challenges for this user
    challenges = Challenge.objects.filter(user=request.user)
    print(f"🔍 DEBUG: Challenges for user: {challenges.count()}")
    for challenge in challenges:
        print(f"  - Challenge: {challenge.skill.name} | Status: {challenge.status} | ID: {challenge.id}")
    
    # Check session data
    print(f"🔍 DEBUG: Session keys: {list(request.session.keys())}")
    
    return HttpResponse(f"""
    <h3>Debug Information</h3>
    <p>User: {request.user.username}</p>
    <p>Total Skills in DB: {skills.count()}</p>
    <p>Challenges for user: {challenges.count()}</p>
    <ul>
    {"".join([f'<li>{challenge.skill.name} - {challenge.status}</li>' for challenge in challenges])}
    </ul>
    <a href="/challenges/">Go to challenges page</a>
    """)