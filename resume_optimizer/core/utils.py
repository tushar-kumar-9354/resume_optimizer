# core/utils.py
import re
import fitz  # PyMuPDF
import google.generativeai as genai
from core.models import Skill, Challenge
from django.conf import settings
import json

# Configure Gemini API
genai.configure(api_key="AIzaSyDUKAYNttTpvyilioaF9BfbPDEmw6g2ljQ")
model = genai.GenerativeModel("models/gemini-1.5-flash-latest")

def extract_resume_text(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    return "\n".join(page.get_text() for page in doc)

def extract_skills(text):
    known_skills = [
        'Python', 'Django', 'JavaScript', 'React', 'SQL',
        'Node.js', 'Flask', 'Machine Learning', 'Data Analysis'
    ]
    return [skill for skill in known_skills if re.search(rf'\b{re.escape(skill)}\b', text, re.IGNORECASE)]

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

Each question should be a fill-in-the-blank type asking the user to complete a line of code or choose the correct syntax.

Required format:
{{
  "mcqs": [
    {{
      "question": "Complete the syntax: print(___)",
      "options": ["'Hello World'", "print", "()", "'()'"],
      "answer": "'Hello World'"
    }},
    {{
      "question": "Fill in the blank: for i ___ range(5):",
      "options": ["on", "in", "of", "into"],
      "answer": "in"
    }},
    {{
      "question": "Select correct syntax: def ___():",
      "options": ["main", "func", "__init__", "function"],
      "answer": "main"
    }},
    {{
      "question": "Fill in: if a ___ b:",
      "options": ["=", "==", "!=", "<>"],
      "answer": "=="
    }},
    {{
      "question": "Complete line: import ___",
      "options": ["python", "os", "from", "sys.path"],
      "answer": "os"
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