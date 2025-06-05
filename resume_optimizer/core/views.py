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