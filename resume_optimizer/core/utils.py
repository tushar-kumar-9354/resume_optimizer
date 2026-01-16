# core/utils.py
import re
import fitz  # PyMuPDF
import google.generativeai as genai
from core.models import Skill, Challenge
import json
import time

# Store the last API call time to prevent rate limiting
last_api_call_time = 0
MIN_API_CALL_INTERVAL = 1  # seconds

def safe_api_call():
    """Ensure we don't make API calls too quickly"""
    global last_api_call_time
    current_time = time.time()
    if current_time - last_api_call_time < MIN_API_CALL_INTERVAL:
        time.sleep(MIN_API_CALL_INTERVAL - (current_time - last_api_call_time))
    last_api_call_time = time.time()

def get_gemini_model(api_key=None, model_name="gemma-3-1b-it"):
    """Get Gemini model with optional API key"""
    if api_key:
        genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)

def extract_resume_text(file):
    """Extract text from PDF resume"""
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

def extract_skills(text, api_key=None):
    """Extract skills from resume text with better error handling"""
    prompt = f"""
Extract main technical skills from this resume text.
Return ONLY a JSON array of skill names.
Example: ["Python", "JavaScript", "Django"]

Resume text:
{text[:2000]}
"""
    try:
        safe_api_call()
        model = get_gemini_model(api_key, "gemma-3-1b-it")
        response = model.generate_content(prompt)
        cleaned = response.text.strip()
        
        # Clean the response
        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1].strip()
        
        # Try to parse as JSON
        try:
            skills = json.loads(cleaned)
            if isinstance(skills, list):
                print(f"✅ Extracted skills: {skills}")
                return [skill for skill in skills if skill and isinstance(skill, str)][:5]
        except json.JSONDecodeError:
            # Try alternative parsing
            skills = []
            # Look for array-like patterns
            match = re.search(r'\[(.*?)\]', cleaned, re.DOTALL)
            if match:
                skills_str = match.group(1)
                skills = [s.strip().strip('"\'') for s in skills_str.split(',') if s.strip()]
            
            if not skills:
                # Extract skills from text
                common_skills = ['Python', 'JavaScript', 'Java', 'SQL', 'Django', 'React', 
                               'Node.js', 'HTML', 'CSS', 'Git', 'AWS', 'Docker', 'Machine Learning',
                               'Data Analysis', 'Communication', 'Teamwork', 'Problem Solving']
                for skill in common_skills:
                    if skill.lower() in text.lower() and len(skills) < 5:
                        skills.append(skill)
            
            print(f"⚠️  Parsed skills (fallback): {skills[:5]}")
            return skills[:5]
            
    except Exception as e:
        print(f"❌ Error extracting skills: {e}")
        print(f"Response was: {cleaned if 'cleaned' in locals() else 'No response'}")
    
    # Ultimate fallback
    return ['Python', 'Problem Solving', 'Communication']

def extract_projects(text):
    """Extract project descriptions from resume"""
    # Look for project sections
    projects = re.findall(r'(?i)(?:Project\s*[:\-]?\s*|•\s*)([^\.]+\.)', text)
    projects += re.findall(r'(?i)Developed\s+(.+?\.)', text)
    projects += re.findall(r'(?i)Built\s+(.+?\.)', text)
    return projects[:5]  # Return max 5 projects

def extract_experience(text):
    """Extract work experience from resume"""
    experience = re.findall(r'(?i)(?:Experience\s*[:\-]?\s*|Worked\s+at\s+)([^\.]+\.)', text)
    experience += re.findall(r'(?i)(?:Role\s*[:\-]?\s*|Position\s*[:\-]?\s*)([^\.]+\.)', text)
    return experience[:5]  # Return max 5 experiences


def analyze_resume(resume_text, api_key=None):
    """Analyze resume and identify skills needing demonstration - simplified"""
    print(f"📄 Analyzing resume text (length: {len(resume_text)})")
    
    # Extract skills with limit
    all_skills = extract_skills(resume_text, api_key)
    skills = all_skills[:4]  # Limit to 4 skills
    print(f"📝 Skills to check: {skills}")
    
    # Extract projects and experience
    projects = extract_projects(resume_text)
    experiences = extract_experience(resume_text)
    
    print(f"📂 Found {len(projects)} projects, {len(experiences)} experiences")
    
    feedback = []
    for skill in skills:
        if not skill or not isinstance(skill, str):
            continue
            
        skill_lower = skill.lower()
        demonstrated = False
        
        # Check if skill is demonstrated in projects
        for project in projects:
            if skill_lower in project.lower():
                demonstrated = True
                print(f"✅ Skill '{skill}' found in project: {project[:50]}...")
                break
        
        # Check if skill is demonstrated in experiences
        if not demonstrated:
            for exp in experiences:
                if skill_lower in exp.lower():
                    demonstrated = True
                    print(f"✅ Skill '{skill}' found in experience: {exp[:50]}...")
                    break
        
        if not demonstrated:
            reason = f"{skill} is listed but not demonstrated through projects or work experience."
            print(f"⚠️  Skill '{skill}' needs demonstration")
            
            # Create simple feedback with only MCQs
            feedback.append({
                "skill": skill,
                "reason": reason,
                "mcqs": [
                    {
                        "question": f"What is important when working with {skill}?",
                        "options": ["Planning", "Testing", "Documentation", "All of the above"],
                        "answer": "All of the above"
                    },
                    {
                        "question": f"Which practice improves {skill} proficiency?",
                        "options": ["Regular practice", "Reading documentation", "Code review", "All of the above"],
                        "answer": "All of the above"
                    }
                ]
            })
    
    print(f"📊 Generated feedback for {len(feedback)} skills")
    return feedback

def generate_challenges_from_feedback(user, feedback_list, api_key=None):
    """Generate challenges from feedback - compatible with current model"""
    created_count = 0
    print(f"🚀 Starting challenge generation for {len(feedback_list)} skills")
    
    if not feedback_list:
        print("📭 No feedback provided for challenge generation")
        return 0
    
    for feedback in feedback_list:
        try:
            skill_name = feedback["skill"].strip().title()
            reason = feedback["reason"]
            description = f"Demonstrate your {skill_name} skills in a practical project"
            
            print(f"🎯 Processing skill: {skill_name}")
            
            # Get or create skill
            skill_obj, created = Skill.objects.get_or_create(
                name=skill_name
            )
            
            # Check if challenge already exists
            existing_challenge = Challenge.objects.filter(
                user=user,
                skill=skill_obj,
                description__icontains=skill_name
            ).first()
            
            if existing_challenge:
                print(f"⏭️  Challenge for '{skill_name}' already exists, skipping...")
                continue
            
            # Get MCQs from feedback
            mcqs = feedback.get("mcqs", [])
            if not mcqs:
                # Create default MCQs if none provided
                mcqs = [
                    {
                        "question": f"What is important when working with {skill_name}?",
                        "options": ["Planning", "Testing", "Documentation", "All of the above"],
                        "answer": "All of the above"
                    },
                    {
                        "question": f"Which tool can help with {skill_name}?",
                        "options": ["Version Control", "Text Editor", "Debugger", "All of the above"],
                        "answer": "All of the above"
                    }
                ]
            
            # Create challenge WITHOUT fill_in_blanks field
            challenge = Challenge.objects.create(
                user=user,
                skill=skill_obj,
                reason=reason,
                description=description,
                mcq_questions=mcqs,  # Only store MCQs
                status="PENDING"
            )
            
            created_count += 1
            print(f"✅ Created challenge: {skill_name} (ID: {challenge.id})")
            
        except Exception as e:
            print(f"❌ Error creating challenge for {feedback.get('skill', 'unknown')}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"🎉 Total challenges created: {created_count}")
    return created_count

def generate_projects_based_on_skills(skills, api_key=None):
    """Generate project ideas based on skills"""
    if not skills:
        skills = ['Python', 'Problem Solving']
    
    prompt = f"""
Based on these skills: {', '.join(skills[:3])}
Suggest 2 simple project ideas.

Format as JSON array with 'title', 'description', and 'technologies' fields.

Example:
[
{{
    "title": "Personal Portfolio Website",
    "description": "Create a portfolio website to showcase your projects and skills.",
    "technologies": "HTML, CSS, JavaScript"
}}
]
"""
    try:
        safe_api_call()
        model = get_gemini_model(api_key, "gemma-3-1b-it")
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        # Clean the response
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        
        projects = json.loads(content)
        print(f"✅ Generated {len(projects)} project ideas")
        return projects
        
    except Exception as e:
        print(f"❌ Project generation failed: {e}")
        # Return default projects
        return [
            {
                "title": "Personal Portfolio Website",
                "description": "Build a website to showcase your resume, projects, and skills.",
                "technologies": "HTML, CSS, JavaScript"
            },
            {
                "title": "Task Management App",
                "description": "Create an app to manage daily tasks and track progress.",
                "technologies": "Python, Django, SQLite"
            }
        ]

def generate_project_plan(project_title, description, skills, api_key=None):
    """Generate project execution plan"""
    prompt = f"""
Create a simple 4-week plan for: {project_title}
Description: {description}
Skills: {', '.join(skills[:3])}

Return as JSON array with 'week' and 'task' fields.
"""
    try:
        safe_api_call()
        model = get_gemini_model(api_key, "gemma-3-1b-it")
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        
        plan = json.loads(content)
        print(f"✅ Generated {len(plan)}-week plan for '{project_title}'")
        return plan
        
    except Exception as e:
        print(f"❌ Plan generation failed: {e}")
        return [
            {"week": 1, "task": "Setup project structure and basic files"},
            {"week": 2, "task": "Implement core functionality"},
            {"week": 3, "task": "Add user interface and styling"},
            {"week": 4, "task": "Testing and deployment"}
        ]


def generate_code_for_step(project_title, task_description, skills, api_key=None):
    """Generate code for a project step with better error handling"""
    if not skills:
        skills = ["Python", "Programming"]
    
    prompt = f"""
Project: {project_title}
Task: {task_description}
Skills: {', '.join(skills[:3])}

Provide simple code implementation with comments.
If it's a complex task, provide a basic template or outline.

Format your response clearly.
"""
    try:
        safe_api_call()
        model = get_gemini_model(api_key, "gemma-3-1b-it")
        response = model.generate_content(prompt)
        code = response.text.strip()
        
        if not code or len(code) < 10:
            code = f"""# Code for: {task_description}

# This is a placeholder for your implementation
# Based on your project: {project_title}

def main():
    print("Implement your {task_description} here")
    
    # Add your code based on the requirements
    # Use the skills: {', '.join(skills[:3])}

if __name__ == "__main__":
    main()
"""
        
        print(f"✅ Generated code for: {task_description}")
        return code
        
    except Exception as e:
        print(f"❌ Code generation failed: {e}")
        # Return a simple template
        return f"""# Code Implementation for: {task_description}

# Project: {project_title}
# Required Skills: {', '.join(skills[:3])}

"""

def log_activity(user, activity_type, title, details=""):
    """Log user activity"""
    from django.utils import timezone
    from .models import Activity
    
    try:
        Activity.objects.create(
            user=user,
            activity_type=activity_type,
            title=title,
            details=details,
            timestamp=timezone.now()
        )
        print(f"📝 Logged activity: {activity_type} - {title}")
    except Exception as e:
        print(f"❌ Failed to log activity: {e}")