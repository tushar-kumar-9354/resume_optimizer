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

    Required format:
    {{
    "theory": "Short theoretical question about {skill}",
    "mcq": {{
        "question": "MCQ question about {skill}",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "answer": "Correct option text"
    }}
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
                    feedback.append({
                        "skill": skill,
                        "reason": reason,
                        "theory": structured.get("theory", ""),
                        "mcq": {
                            "question": structured.get("mcq", {}).get("question", ""),
                            "options": structured.get("mcq", {}).get("options", []),
                            "answer": structured.get("mcq", {}).get("answer", "")
                        }
                    })
                except json.JSONDecodeError:
                    print(f"⚠️ Invalid JSON for skill {skill}:\n{gemini_output}")
                except Exception as e:
                    print(f"❌ Failed to parse Gemini output for {skill}:", e)

    return feedback

# core/utils.py (updated generate_challenges_from_feedback function)
def generate_challenges_from_feedback(user, feedback_list):
    created_count = 0
    for feedback in feedback_list:
        skill_name = feedback["skill"].title()
        reason = feedback["reason"]
        description = f"Create a project demonstrating your {skill_name} skills. Reason: {reason}"

        skill_obj, _ = Skill.objects.get_or_create(name=skill_name)

        if Challenge.objects.filter(user=user, skill=skill_obj, description=description).exists():
            continue

        # Create with proper data structure
        Challenge.objects.create(
            user=user,
            skill=skill_obj,
            reason=reason,
            description=description,
            theory_questions=[feedback.get("theory", "")],
            mcq_questions=[{
                "question": feedback["mcq"]["question"],
                "options": feedback["mcq"]["options"],
                "answer": feedback["mcq"]["answer"]
            }],
            status="PENDING"
        )
        created_count += 1
    return created_count