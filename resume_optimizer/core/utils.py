# core/utils.py
import re
import fitz  # PyMuPDF
import google.generativeai as genai
from core.models import Skill, Challenge
from django.conf import settings
import json

# Configure Gemini API
genai.configure(api_key="AIzaSyDlgaheySCnhuZlUF8uUUr7pKihdmcdWKM")
model = genai.GenerativeModel("models/gemini-2.0-flash")

def extract_resume_text(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    return "\n".join(page.get_text() for page in doc)

import ast

def extract_skills(text):
    prompt = f"""
You are a resume parser. Extract main technical and non-technical skills from the following resume text. 
Only return a clean Python list of skills like ["Skill1", "Skill2"], no markdown or explanation.

Resume:
\"\"\"
{text}
\"\"\"
"""
    try:
        response = model.generate_content(prompt)
        cleaned = response.text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```python", "").replace("```", "").strip()
        return ast.literal_eval(cleaned)
    except Exception as e:
        print("Error extracting skills:", e)
        return []


def extract_projects(text):
    return re.findall(r'(?i)(?:Project\s*[:\-]?\s*)(.*)', text)

def extract_experience(text):
    experience = re.findall(r'(?i)(?:Experience\s*[:\-]?\s*)(.*)', text)
    experience += re.findall(r'(?i)(?:Worked at\s*)(.*)', text)
    return experience
def ask_gemini_for_challenge(skill, reason):
    prompt = f"""
The user listed "{skill}" in their resume but has not demonstrated it in projects or work experience.

Generate a JSON response ONLY, without explanations.

The JSON should include:
- 2 fill-in-the-blank questions (no options — user types the answer)
- 2 multiple-choice questions (MCQ with 4 options)

⚠️ Make questions relevant to the skill, regardless of domain (e.g., if skill is "Marketing", "Economics", "Public Speaking", or "Leadership").

Use this format exactly:
{{
  "fill_in_the_blanks": [
    {{
      "question": "Fill in the blank question 1 about {skill}",
      "answer": "Correct answer"
    }},
    ...
    {{
      "question": "Fill in the blank question 5 about {skill}",
      "answer": "Correct answer"
    }}
  ],
  "mcqs": [
    {{
      "question": "MCQ question 1 about {skill}",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option text"
    }},
    ...
    {{
      "question": "MCQ question 5 about {skill}",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option text"
    }}
  ]
}}
"""
    response = model.generate_content(prompt)
    try:
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        print("Gemini output error:", e)
        return None

def clean_gemini_json(gemini_output):
    """
    Remove markdown formatting like ```json ... ``` if present.
    """
    return re.sub(r"^```json|```$", "", gemini_output.strip(), flags=re.MULTILINE).strip()

def analyze_resume(resume_text):
    skills = extract_skills(resume_text)
    print("Extracted skills:", skills)
    projects = extract_projects(resume_text)
    experiences = extract_experience(resume_text)

    feedback = []
    for skill in skills:
        demonstrated = any(skill.lower() in p.lower() for p in projects) or \
                       any(skill.lower() in e.lower() for e in experiences)
        print(f"Skill: {skill}, Demonstrated: {demonstrated}")
        
        if not demonstrated:
            reason = f"{skill} is listed but not demonstrated through projects or work experience."
            gemini_output = ask_gemini_for_challenge(skill, reason)

            if gemini_output:
                print(f"🧾 Raw Gemini output for {skill}:\n{gemini_output}")
                try:
                    cleaned_output = clean_gemini_json(gemini_output)
                    structured = json.loads(cleaned_output)
                    
                    # Fix: Properly handle the mcqs array from Gemini
                    feedback.append({
                        "skill": skill,
                        "reason": reason,
                        "mcqs": structured.get("mcqs", [])  # Get all MCQs from the response
                    })
                except json.JSONDecodeError:
                    print(f"⚠️ Invalid JSON for skill {skill}:\n{gemini_output}")
                except Exception as e:
                    print(f"❌ Failed to parse Gemini output for {skill}:", e)

    return feedback
def generate_challenges_from_feedback(user, feedback_list):
    created_count = 0
    for feedback in feedback_list:
        skill_name = feedback["skill"].title()
        reason = feedback["reason"]
        description = f"Create a project demonstrating your {skill_name} skills. Reason: {reason}"

        skill_obj, _ = Skill.objects.get_or_create(name=skill_name)

        if Challenge.objects.filter(user=user, skill=skill_obj, description=description).exists():
            continue

        # Create with all MCQ questions from the feedback
        Challenge.objects.create(
            user=user,
            skill=skill_obj,
            reason=reason,
            description=description,
            mcq_questions=feedback.get("mcqs", []),  # Use all MCQs from the response
            status="PENDING"
        )
        created_count += 1
    return created_count


def generate_dummy_projects(skills):
    prompt = """
    Based on the following skills: Python, Django, React, PostgreSQL, REST APIs, Machine Learning (specifically image classification), and basic mobile development (React Native), suggest 3 realistic and creative final-year software project ideas.

    Each project should include:
    - A short title
    - A 3–5 line detailed description
    - Technologies used

    Format the output in JSON:
    [
    {
        "title": "...",
        "description": "...",
        "technologies": "..."
    },
    ...
    ]
    """

    response = model.generate_content(prompt)
    return response.text
def parse_project_response(response_text):
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return [{
            "title": "Parsing Failed",
            "description": response_text,
            "technologies": "Unknown"
        }]
def generate_project_execution_plan(project_title, description, skills):
    prompt = f"""
You are an expert project mentor.

Give a clear, step-by-step weekly development plan to build this project:
Title: {project_title}
Description: {description}
Skills: {', '.join(skills)}

Return the plan in JSON format like:
[
  {{"week": 1, "task": "Setup backend using Django and PostgreSQL"}},
  {{"week": 2, "task": "Build REST APIs for login and data storage"}},
  ...
]
"""
    response = model.generate_content(prompt)
    try:
        cleaned = response.text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except Exception as e:
        print("❌ Plan parsing error:", e)
        return [{"week": 0, "task": "Failed to generate project plan"}]


def generate_projects_based_on_skills(skills):
    prompt = f"""
You're an AI suggesting unique project ideas for a resume.

Skills: {', '.join(skills)}

Give 3 project ideas in JSON like:
[
  {{
    "title": "AI Recipe Recommender",
    "description": "An app that recommends recipes based on ingredients using ML.",
    "technologies": "Django, TensorFlow, PostgreSQL"
  }},
  ...
]
"""
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text.strip().strip("```json").strip("```"))
    except Exception as e:
        print("Project idea generation failed:", e)
        return []

def generate_project_plan(project_title, description, skills):
    prompt = f"""
Create a 12-week plan to build this project:

Title: {project_title}
Description: {description}
Skills: {', '.join(skills)}

Return JSON like:
[
  {{ "week": 1, "task": "Setup Django and GitHub repo" }},
  ...
]
"""
    try:
        response = model.generate_content(prompt)
        return json.loads(response.text.strip().strip("```json").strip("```"))
    except Exception as e:
        print("Plan generation failed:", e)
        return []
def generate_code_for_step(project_title, task_description, skills, previous_steps=None):
    previous_steps = previous_steps or []
    history_context = "\n".join(f"- {step}" for step in previous_steps if step != task_description)

    prompt = f"""
You are an expert full‑stack mentor.

Project: {project_title}
Skills: {', '.join(skills)}
Completed Steps: {history_context}

🔧 TASK:
Implement this step: "{task_description}"

INSTRUCTIONS:
• Specify **each file** affected (e.g., models.py, views.py, urls.py, serializers.py).
• Clearly indicate **where to put** the code (top of file, under imports, within a class/method).
• Provide **only working code blocks**, **no pseudocode**. Use fenced code blocks (```python, ```js).
• Begin each section with file reference:
    💾 **Write this in `models.py`**:
    ```python
    ...
    ```
• Keep blocks modular and beginner‑friendly.

Now generate the code.
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Code generation error: {e}"
from django.utils import timezone
from .models import Activity

def log_activity(user, activity_type, title, details=""):
    """
    Logs a new activity for the user
    """
    Activity.objects.create(
        user=user,
        activity_type=activity_type,
        title=title,
        details=details,
        timestamp=timezone.now()
    )
    
    # Keep only the last 20 activities per user
    activities_to_delete = Activity.objects.filter(user=user).order_by('-timestamp')[20:].iterator()
   