# app.py - Main Application File

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import re
import json
import hashlib
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from PyPDF2 import PdfReader
from docx import Document  # Changed from docx2txt to python-docx
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import plotly.graph_objects as go
import plotly.express as px
from streamlit_option_menu import option_menu
import sqlite3
import io

# Page configuration
st.set_page_config(
    page_title="AI Resume Analyzer Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Dark mode support */
    @media (prefers-color-scheme: dark) {
        :root {
            --primary-color: #4CAF50;
            --secondary-color: #2196F3;
        }
    }
    
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(45deg, #4CAF50, #2196F3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .skill-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        margin: 0.25rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 500;
    }
    
    .skill-found {
        background-color: #4CAF50;
        color: white;
    }
    
    .skill-missing {
        background-color: #f44336;
        color: white;
    }
    
    .checklist-item {
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
    }
    
    .success-check {
        color: #4CAF50;
        font-weight: bold;
    }
    
    .warning-check {
        color: #ff9800;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'report_history' not in st.session_state:
    st.session_state.report_history = []
if 'current_theme' not in st.session_state:
    st.session_state.current_theme = 'light'
if 'selected_roles' not in st.session_state:
    st.session_state.selected_roles = []

# Database setup
def init_database():
    conn = sqlite3.connect('resume_analyzer.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  email TEXT,
                  created_at TIMESTAMP)''')
    
    # Reports table
    c.execute('''CREATE TABLE IF NOT EXISTS reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  resume_score INTEGER,
                  ats_score INTEGER,
                  match_score REAL,
                  skills_found TEXT,
                  missing_skills TEXT,
                  created_at TIMESTAMP,
                  role TEXT)''')
    
    # Resume history table
    c.execute('''CREATE TABLE IF NOT EXISTS resume_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  resume_text TEXT,
                  parsed_data TEXT,
                  created_at TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_database()

# Helper function to extract text from DOCX
def extract_text_from_docx(docx_file):
    doc = Document(docx_file)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

# Authentication functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    conn = sqlite3.connect('resume_analyzer.db')
    c = conn.cursor()
    hashed = hash_password(password)
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hashed))
    user = c.fetchone()
    conn.close()
    return user is not None

def register_user(username, password, email):
    conn = sqlite3.connect('resume_analyzer.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, email, created_at) VALUES (?,?,?,?)",
                  (username, hash_password(password), email, datetime.now()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def save_report(username, resume_score, ats_score, match_score, skills_found, missing_skills, role):
    conn = sqlite3.connect('resume_analyzer.db')
    c = conn.cursor()
    c.execute("INSERT INTO reports (username, resume_score, ats_score, match_score, skills_found, missing_skills, created_at, role) VALUES (?,?,?,?,?,?,?,?)",
              (username, resume_score, ats_score, match_score, 
               json.dumps(skills_found), json.dumps(missing_skills), datetime.now(), role))
    conn.commit()
    conn.close()

# Expanded skills database by role
skills_by_role = {
    "AI Engineer": ["python", "machine learning", "deep learning", "tensorflow", "pytorch", "nlp", "computer vision", "llm", "transformers", "langchain", "rag", "vector databases", "model deployment", "mlops"],
    "Data Scientist": ["python", "r", "sql", "machine learning", "statistics", "data visualization", "pandas", "numpy", "scikit-learn", "tableau", "power bi", "big data", "hadoop", "spark"],
    "Data Analyst": ["python", "sql", "excel", "tableau", "power bi", "data visualization", "statistics", "pandas", "numpy", "business intelligence", "reporting", "etl"],
    "ML Engineer": ["python", "machine learning", "mlops", "docker", "kubernetes", "ci/cd", "model serving", "tensorflow", "pytorch", "cloud platforms", "aws", "azure", "gcp"],
    "Backend Developer": ["python", "java", "node.js", "sql", "nosql", "rest api", "microservices", "docker", "kubernetes", "aws", "django", "flask", "spring boot"],
    "Full Stack Developer": ["javascript", "react", "node.js", "python", "html", "css", "mongodb", "postgresql", "git", "rest api", "graphql"],
    "DevOps Engineer": ["docker", "kubernetes", "jenkins", "gitlab", "ci/cd", "aws", "terraform", "ansible", "linux", "prometheus", "grafana", "elk stack"]
}

# Courses for missing skills
skill_courses = {
    "python": ["https://www.coursera.org/learn/python-for-everybody", "https://www.udemy.com/course/100-days-of-code/"],
    "sql": ["https://www.coursera.org/learn/sql-for-data-science", "https://mode.com/sql-tutorial/"],
    "machine learning": ["https://www.coursera.org/learn/machine-learning", "https://www.kaggle.com/learn/machine-learning"],
    "deep learning": ["https://www.deeplearning.ai/", "https://www.coursera.org/specializations/deep-learning"],
    "docker": ["https://docker-curriculum.com/", "https://www.coursera.org/learn/docker"],
    "kubernetes": ["https://kubernetes.io/docs/tutorials/", "https://www.udemy.com/course/kubernetes-for-beginners/"],
    "tableau": ["https://www.tableau.com/learn/training", "https://www.coursera.org/learn/data-visualization-tableau"],
    "power bi": ["https://docs.microsoft.com/en-us/power-bi/", "https://www.coursera.org/learn/power-bi"]
}

# Resume parsing
def parse_resume(text):
    parsed_data = {
        'name': None,
        'email': None,
        'phone': None,
        'linkedin': None,
        'github': None,
        'experience_years': None,
        'education': [],
        'certifications': [],
        'projects': []
    }
    
    # Extract name (simple heuristic - first line or common patterns)
    lines = text.split('\n')
    if lines:
        # Often the name is in the first few lines and is not too long
        for line in lines[:5]:
            line = line.strip()
            if len(line) < 30 and len(line) > 3 and not any(x in line.lower() for x in ['resume', 'curriculum', 'vitae', 'email', 'phone']):
                parsed_data['name'] = line.title()
                break
    
    # Extract email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    if emails:
        parsed_data['email'] = emails[0]
    
    # Extract phone
    phone_pattern = r'\b(?:\+?91)?\s*[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{4}\b'
    phones = re.findall(phone_pattern, text)
    if phones:
        parsed_data['phone'] = phones[0]
    
    # Extract LinkedIn
    linkedin_pattern = r'linkedin\.com/in/[\w-]+'
    linkedin = re.findall(linkedin_pattern, text)
    if linkedin:
        parsed_data['linkedin'] = linkedin[0]
    
    # Extract GitHub
    github_pattern = r'github\.com/[\w-]+'
    github = re.findall(github_pattern, text)
    if github:
        parsed_data['github'] = github[0]
    
    # Extract experience (years)
    exp_patterns = [
        r'(\d+)\+?\s*years?\s+of\s+experience',
        r'experience\s+of\s+(\d+)\+?\s*years?',
        r'worked\s+for\s+(\d+)\+?\s*years?'
    ]
    
    for pattern in exp_patterns:
        match = re.search(pattern, text.lower())
        if match:
            parsed_data['experience_years'] = int(match.group(1))
            break
    
    # Extract education
    education_keywords = ['b.tech', 'm.tech', 'b.e', 'm.e', 'b.sc', 'm.sc', 'bca', 'mca', 'phd', 'bachelor', 'master', 'degree']
    education_sentences = []
    for keyword in education_keywords:
        if keyword in text.lower():
            # Get surrounding context
            idx = text.lower().find(keyword)
            start = max(0, idx - 50)
            end = min(len(text), idx + 100)
            education_sentences.append(text[start:end])
    parsed_data['education'] = education_sentences[:3]
    
    # Extract certifications
    cert_keywords = ['certification', 'certified', 'certificate', 'coursera', 'udemy', 'udacity', 'edx']
    certs = []
    for keyword in cert_keywords:
        if keyword in text.lower():
            idx = text.lower().find(keyword)
            start = max(0, idx - 30)
            end = min(len(text), idx + 50)
            certs.append(text[start:end])
    parsed_data['certifications'] = certs[:5]
    
    # Extract projects
    project_keywords = ['project', 'developed', 'built', 'created', 'implemented']
    projects = []
    for keyword in project_keywords:
        if keyword in text.lower():
            idx = text.lower().find(keyword)
            start = max(0, idx - 20)
            end = min(len(text), idx + 100)
            projects.append(text[start:end])
    parsed_data['projects'] = projects[:5]
    
    return parsed_data

# Job role prediction
def predict_job_role(text, skills_found):
    role_scores = {}
    
    for role, required_skills in skills_by_role.items():
        matched_skills = [skill for skill in skills_found if skill in required_skills]
        score = (len(matched_skills) / len(required_skills)) * 100 if required_skills else 0
        role_scores[role] = score
    
    # Get top 3 roles
    top_roles = sorted(role_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    return top_roles

# Resume ranking
def rank_resume(parsed_data):
    rank_score = 0
    max_score = 10
    checklist = []
    
    # Name present
    if parsed_data['name']:
        rank_score += 1
        checklist.append({"item": "Name included", "status": "✅"})
    else:
        checklist.append({"item": "Name included", "status": "❌", "suggestion": "Add your full name at the top"})
    
    # Email present
    if parsed_data['email']:
        rank_score += 1
        checklist.append({"item": "Email included", "status": "✅"})
    else:
        checklist.append({"item": "Email included", "status": "❌", "suggestion": "Add your professional email"})
    
    # Phone present
    if parsed_data['phone']:
        rank_score += 1
        checklist.append({"item": "Phone number included", "status": "✅"})
    else:
        checklist.append({"item": "Phone number included", "status": "❌", "suggestion": "Add your contact number"})
    
    # LinkedIn present
    if parsed_data['linkedin']:
        rank_score += 1
        checklist.append({"item": "LinkedIn profile included", "status": "✅"})
    else:
        checklist.append({"item": "LinkedIn profile included", "status": "⚠️", "suggestion": "Add LinkedIn URL for better visibility"})
    
    # GitHub present
    if parsed_data['github']:
        rank_score += 1
        checklist.append({"item": "GitHub profile included", "status": "✅"})
    else:
        checklist.append({"item": "GitHub profile included", "status": "⚠️", "suggestion": "Add GitHub URL to showcase projects"})
    
    # Experience mentioned
    if parsed_data['experience_years']:
        rank_score += 2
        checklist.append({"item": "Experience clearly mentioned", "status": "✅"})
    else:
        checklist.append({"item": "Experience clearly mentioned", "status": "❌", "suggestion": "Clearly mention years of experience"})
    
    # Education section
    if parsed_data['education']:
        rank_score += 1
        checklist.append({"item": "Education section present", "status": "✅"})
    else:
        checklist.append({"item": "Education section present", "status": "❌", "suggestion": "Add your educational qualifications"})
    
    # Certifications
    if parsed_data['certifications']:
        rank_score += 1
        checklist.append({"item": "Certifications listed", "status": "✅"})
    else:
        checklist.append({"item": "Certifications listed", "status": "⚠️", "suggestion": "Add relevant certifications"})
    
    # Projects
    if parsed_data['projects']:
        rank_score += 1
        checklist.append({"item": "Projects section present", "status": "✅"})
    else:
        checklist.append({"item": "Projects section present", "status": "❌", "suggestion": "Add project work to showcase skills"})
    
    percentage = (rank_score / max_score) * 100
    
    # Improvement suggestions
    suggestions = [item['suggestion'] for item in checklist if 'suggestion' in item]
    
    return percentage, checklist, suggestions

# AI Career Roadmap Generator (simplified - requires API key)
def generate_career_roadmap(skills_found, role, experience_years):
    roadmap = f"""
    # Career Roadmap for {role}
    
    ## Current Profile
    - Role: {role}
    - Experience: {experience_years if experience_years else 'Entry level'} years
    - Skills: {', '.join(skills_found[:10])}
    
    ## Short-term Goals (0-6 months)
    - Master core {', '.join(skills_found[:3])} skills
    - Complete 2-3 portfolio projects
    - Obtain relevant certifications
    - Network with industry professionals
    
    ## Medium-term Goals (6-18 months)
    - Lead a significant project
    - Mentor junior team members
    - Contribute to open source
    - Build personal brand through content
    
    ## Long-term Goals (18-36 months)
    - Become subject matter expert
    - Transition to senior/lead role
    - Speak at conferences
    - Build a team or start consulting
    
    ## Recommended Certifications
    - Industry-recognized certifications in your domain
    - Cloud platform certifications (AWS, Azure, GCP)
    - Project management (PMP, Scrum Master)
    
    ## Learning Resources
    - Online courses (Coursera, Udemy, edX)
    - Technical books and documentation
    - Community forums and meetups
    - Hands-on projects and hackathons
    
    ## Project Recommendations
    1. Build an end-to-end application
    2. Create a portfolio showcasing your skills
    3. Contribute to an open-source project
    4. Develop a solution to a real-world problem
    """
    return roadmap

# AI Interview Questions (simplified)
def generate_interview_questions(role, skills_found, experience):
    questions = f"""
    # Interview Questions for {role}
    
    ## Technical Questions ({experience} years experience)
    1. Explain the architecture of a {role} system you've worked on.
    2. How would you optimize a slow-performing {skills_found[0] if skills_found else 'system'}?
    3. Describe a challenging technical problem you solved and your approach.
    
    ## Behavioral Questions
    1. Tell me about a time you had to meet a tight deadline.
    2. How do you handle disagreements with team members?
    3. Describe a situation where you took initiative beyond your role.
    
    ## Problem-Solving Questions
    1. How would you design a solution for [specific business problem]?
    2. Walk me through how you'd debug a critical production issue.
    
    ## System Design Questions
    1. Design a scalable system for [common use case].
    2. How would you architect a microservices-based application?
    
    ## Preparation Tips
    - Review core concepts in {', '.join(skills_found[:5])}
    - Practice with mock interviews
    - Prepare questions for the interviewer
    - Research the company's tech stack
    """
    return questions

# AI Cover Letter Generator (simplified)
def generate_cover_letter(name, role, company, skills_found, experience):
    letter = f"""
    Dear Hiring Manager,

    I am writing to express my strong interest in the {role} position at {company}. 
    With {experience} years of experience and expertise in {', '.join(skills_found[:5])}, 
    I am confident in my ability to contribute to your team.

    Throughout my career, I have developed strong skills in:
    • {skills_found[0] if len(skills_found) > 0 else 'Technical skills'}
    • {skills_found[1] if len(skills_found) > 1 else 'Problem-solving'}
    • {skills_found[2] if len(skills_found) > 2 else 'Team collaboration'}

    I am particularly excited about this opportunity because [company name] is known for 
    innovation and excellence in the industry. I look forward to bringing my experience 
    and enthusiasm to your team.

    Thank you for considering my application. I would welcome the opportunity to discuss 
    how my skills align with your needs.

    Sincerely,
    {name if name else '[Your Name]'}
    """
    return letter

# AI LinkedIn Profile Generator (simplified)
def generate_linkedin_content(name, role, skills_found, experience):
    headline = f"{role} | {', '.join(skills_found[:3])} | {experience} years of experience"
    
    about = f"""
    Passionate {role} with {experience} years of experience in building innovative solutions.
    
    Core competencies include:
    • {', '.join(skills_found[:5])}
    • End-to-end project delivery
    • Cross-functional team collaboration
    
    I'm driven by solving complex problems and creating value through technology. 
    Currently seeking opportunities to leverage my skills in a challenging environment.
    
    Let's connect! 🚀
    """
    
    return f"**Headline:** {headline}\n\n**About Section:**\n{about}"

# Template recommendation
def recommend_template(role, experience_years):
    templates = {
        "Entry Level": {
            "name": "Modern Minimalist",
            "style": "Clean, skills-focused layout",
            "color": "Blue/Teal",
            "link": "https://www.overleaf.com/latex/templates/modern-cv/nqjggpjqqyhd"
        },
        "Mid Level": {
            "name": "Professional Corporate",
            "style": "Experience-driven layout",
            "color": "Navy/Gray",
            "link": "https://www.overleaf.com/latex/templates/professional-cv/nkhrhkkxxyzt"
        },
        "Senior Level": {
            "name": "Executive Profile",
            "style": "Leadership-focused layout",
            "color": "Dark Blue/Burgundy",
            "link": "https://www.overleaf.com/latex/templates/executive-resume/gzbymkpyjngt"
        }
    }
    
    if experience_years and experience_years > 8:
        return templates["Senior Level"]
    elif experience_years and experience_years > 3:
        return templates["Mid Level"]
    else:
        return templates["Entry Level"]

# Radar chart for skills
def create_radar_chart(skills_found, role):
    if role in skills_by_role:
        required_skills = skills_by_role[role][:8]  # Top 8 skills
        current_scores = []
        
        for skill in required_skills:
            if skill in skills_found:
                current_scores.append(100)
            else:
                current_scores.append(0)
        
        fig = go.Figure(data=go.Scatterpolar(
            r=current_scores,
            theta=required_skills,
            fill='toself',
            name='Your Skills',
            line_color='#4CAF50'
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )),
            showlegend=True,
            title=f"Skills Analysis for {role} Role",
            height=500
        )
        
        return fig
    return None

# Main application
def main():
    # Sidebar navigation
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/resume.png", width=80)
        
        selected = option_menu(
            menu_title="Navigation",
            options=["Home", "Dashboard", "Reports", "Analytics", "Settings"],
            icons=["house", "bar-chart", "file-text", "graph-up", "gear"],
            menu_icon="cast",
            default_index=0,
        )
        
        # Theme toggle
        theme = st.toggle("🌙 Dark Mode", value=st.session_state.current_theme == 'dark')
        if theme:
            st.session_state.current_theme = 'dark'
        else:
            st.session_state.current_theme = 'light'
    
    if selected == "Home":
        home_page()
    elif selected == "Dashboard":
        dashboard_page()
    elif selected == "Reports":
        reports_page()
    elif selected == "Analytics":
        if st.session_state.authenticated:
            analytics_page()
        else:
            st.warning("Please login to access analytics")
    elif selected == "Settings":
        settings_page()

def home_page():
    st.markdown('<div class="main-header">AI Resume Analyzer Pro</div>', unsafe_allow_html=True)
    
    # Login/Register section
    if not st.session_state.authenticated:
        col1, col2 = st.columns(2)
        
        with col1:
            with st.expander("🔐 Login", expanded=True):
                login_username = st.text_input("Username", key="login_user")
                login_password = st.text_input("Password", type="password", key="login_pass")
                
                if st.button("Login", use_container_width=True):
                    if authenticate_user(login_username, login_password):
                        st.session_state.authenticated = True
                        st.session_state.username = login_username
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
        
        with col2:
            with st.expander("📝 Register", expanded=True):
                reg_username = st.text_input("Username", key="reg_user")
                reg_email = st.text_input("Email", key="reg_email")
                reg_password = st.text_input("Password", type="password", key="reg_pass")
                reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
                
                if st.button("Register", use_container_width=True):
                    if reg_password == reg_confirm:
                        if register_user(reg_username, reg_password, reg_email):
                            st.success("Registration successful! Please login.")
                        else:
                            st.error("Username already exists")
                    else:
                        st.error("Passwords don't match")
    else:
        st.success(f"Welcome back, {st.session_state.username}! 👋")
        
        # Resume Upload Section
        col1, col2 = st.columns([2, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "Upload Resume (PDF or DOCX)",
                type=["pdf", "docx"],
                help="Upload your resume for AI-powered analysis"
            )
            
            job_role = st.selectbox(
                "Target Job Role",
                list(skills_by_role.keys()),
                index=0
            )
            
            job_desc = st.text_area(
                "Job Description (Optional for better matching)",
                placeholder="Paste the job description here for detailed analysis...",
                height=150
            )
        
        with col2:
            st.markdown("### Quick Stats")
            st.info("💡 Upload your resume to get:\n- AI-powered analysis\n- Skill gap identification\n- Career recommendations\n- Interview preparation")
            
            if uploaded_file is not None:
                if st.button("🚀 Analyze Resume", type="primary", use_container_width=True):
                    analyze_resume(uploaded_file, job_role, job_desc)

def analyze_resume(uploaded_file, job_role, job_desc):
    with st.spinner("Analyzing your resume..."):
        # Extract text
        if uploaded_file.type == "application/pdf":
            reader = PdfReader(uploaded_file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        else:  # DOCX file
            text = extract_text_from_docx(uploaded_file)
        
        text = text.lower()
        
        # Parse resume
        parsed_data = parse_resume(text)
        
        # Skills detection
        role_skills = skills_by_role.get(job_role, skills_by_role["AI Engineer"])
        found_skills = [skill for skill in role_skills if skill in text]
        missing_skills = [skill for skill in role_skills if skill not in found_skills]
        
        # Calculate scores
        resume_score = (len(found_skills) / len(role_skills)) * 100 if role_skills else 0
        
        # ATS Score
        ats_sections = ["contact", "education", "skills", "experience", "projects", "certifications"]
        found_sections = sum(1 for section in ats_sections if section in text)
        ats_score = (found_sections / len(ats_sections)) * 100
        
        # Match score with job description
        match_score = 0
        if job_desc:
            vectorizer = TfidfVectorizer()
            vectors = vectorizer.fit_transform([text, job_desc.lower()])
            match_score = cosine_similarity(vectors[0:1], vectors[1:2])[0][0] * 100
        
        # Rank resume
        rank_percentage, checklist, suggestions = rank_resume(parsed_data)
        
        # Predict roles
        predicted_roles = predict_job_role(text, found_skills)
        
        # Get template recommendation
        template = recommend_template(job_role, parsed_data['experience_years'])
        
        # Save to database
        if st.session_state.authenticated:
            save_report(st.session_state.username, int(resume_score), int(ats_score), 
                       match_score, found_skills, missing_skills, job_role)
        
        # Display results
        display_results(parsed_data, found_skills, missing_skills, resume_score, 
                       ats_score, match_score, job_role, predicted_roles, 
                       template, checklist, suggestions, text, job_desc)

def display_results(parsed_data, found_skills, missing_skills, resume_score, 
                   ats_score, match_score, job_role, predicted_roles, 
                   template, checklist, suggestions, text, job_desc):
    
    st.success("✅ Analysis Complete!")
    
    # Key Metrics
    st.subheader("📊 Key Metrics")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Resume Score", f"{int(resume_score)}/100", 
                 delta="Excellent" if resume_score > 70 else "Needs Work")
    with col2:
        st.metric("ATS Score", f"{int(ats_score)}/100")
    with col3:
        st.metric("Job Match", f"{int(match_score)}%")
    with col4:
        st.metric("Skills Found", f"{len(found_skills)}/{len(found_skills)+len(missing_skills)}")
    with col5:
        st.metric("Resume Rank", f"{int(100 - len(suggestions)*5)}/100")
    
    # Resume Parsing Results
    with st.expander("📋 Parsed Information", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Contact Information**")
            st.write(f"👤 Name: {parsed_data['name'] or 'Not found'}")
            st.write(f"📧 Email: {parsed_data['email'] or 'Not found'}")
            st.write(f"📱 Phone: {parsed_data['phone'] or 'Not found'}")
            st.write(f"💼 LinkedIn: {parsed_data['linkedin'] or 'Not found'}")
            st.write(f"🐙 GitHub: {parsed_data['github'] or 'Not found'}")
            st.write(f"⏰ Experience: {parsed_data['experience_years'] or 'Not specified'} years")
        
        with col2:
            if parsed_data['education']:
                st.write("**Education**")
                for edu in parsed_data['education'][:2]:
                    st.write(f"• {edu[:100]}...")
            
            if parsed_data['certifications']:
                st.write("**Certifications**")
                for cert in parsed_data['certifications'][:3]:
                    st.write(f"• {cert[:80]}...")
    
    # Skills Analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("✅ Skills Found")
        for skill in found_skills[:10]:
            st.markdown(f'<span class="skill-badge skill-found">{skill}</span>', unsafe_allow_html=True)
    
    with col2:
        st.subheader("❌ Missing Skills")
        for skill in missing_skills[:10]:
            st.markdown(f'<span class="skill-badge skill-missing">{skill}</span>', unsafe_allow_html=True)
            if skill in skill_courses:
                with st.expander(f"📚 Courses for {skill}"):
                    for course in skill_courses[skill]:
                        st.write(f"• [Course Link]({course})")
    
    # Radar Chart
    st.subheader("📈 Skills Radar Chart")
    fig = create_radar_chart(found_skills, job_role)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    
    # Resume Improvement Checklist
    st.subheader("✅ Resume Improvement Checklist")
    checklist_cols = st.columns(2)
    for idx, item in enumerate(checklist):
        with checklist_cols[idx % 2]:
            if item['status'] == '✅':
                st.success(f"{item['status']} {item['item']}")
            elif item['status'] == '⚠️':
                st.warning(f"{item['status']} {item['item']}")
            else:
                st.error(f"{item['status']} {item['item']}")
    
    if suggestions:
        st.info("**Suggestions for Improvement:**")
        for suggestion in suggestions[:5]:
            st.write(f"• {suggestion}")
    
    # Job Role Prediction
    st.subheader("🎯 Predicted Job Roles")
    for role, score in predicted_roles:
        st.progress(score/100)
        st.write(f"{role}: {score:.1f}% match")
    
    # Template Recommendation
    st.subheader("📄 Resume Template Recommendation")
    st.info(f"""
    **{template['name']}** - {template['style']}
    - Color scheme: {template['color']}
    - [View Template]({template['link']})
    """)
    
    # AI Features
    st.subheader("🤖 AI-Powered Features")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Career Roadmap", "Interview Questions", "Cover Letter", "LinkedIn Profile"])
    
    with tab1:
        if st.button("Generate Career Roadmap"):
            roadmap = generate_career_roadmap(found_skills, job_role, parsed_data['experience_years'])
            st.markdown(roadmap)
    
    with tab2:
        if st.button("Generate Interview Questions"):
            questions = generate_interview_questions(job_role, found_skills, parsed_data['experience_years'] or 2)
            st.markdown(questions)
    
    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Target Company", key="cover_company")
        with col2:
            your_name = st.text_input("Your Name", key="cover_name", value=parsed_data['name'] or "")
        
        if st.button("Generate Cover Letter"):
            cover = generate_cover_letter(your_name, job_role, company_name, found_skills, parsed_data['experience_years'] or 2)
            st.markdown(cover)
            st.download_button("Download Cover Letter", cover, file_name="cover_letter.txt")
    
    with tab4:
        if st.button("Generate LinkedIn Content"):
            linkedin_content = generate_linkedin_content(parsed_data['name'], job_role, found_skills, parsed_data['experience_years'] or 2)
            st.markdown(linkedin_content)
    
    # Download Report
    st.subheader("📄 Download Report")
    if st.button("Generate PDF Report"):
        generate_pdf_report(parsed_data, found_skills, missing_skills, resume_score, 
                           ats_score, match_score, job_role, checklist)

def generate_pdf_report(parsed_data, found_skills, missing_skills, resume_score, 
                        ats_score, match_score, job_role, checklist):
    pdf_file = f"resume_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    doc = SimpleDocTemplate(pdf_file, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#4CAF50'))
    story.append(Paragraph("AI Resume Analyzer Report", title_style))
    story.append(Spacer(1, 12))
    
    # Candidate Info
    story.append(Paragraph(f"<b>Name:</b> {parsed_data['name'] or 'Not provided'}", styles['Normal']))
    story.append(Paragraph(f"<b>Email:</b> {parsed_data['email'] or 'Not provided'}", styles['Normal']))
    story.append(Paragraph(f"<b>Target Role:</b> {job_role}", styles['Normal']))
    story.append(Paragraph(f"<b>Report Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Scores
    story.append(Paragraph("<b>SCORES</b>", styles['Heading2']))
    score_data = [
        ['Metric', 'Score'],
        ['Resume Score', f'{int(resume_score)}/100'],
        ['ATS Score', f'{int(ats_score)}/100'],
        ['Job Match', f'{int(match_score)}%'],
        ['Skills Found', f'{len(found_skills)}'],
        ['Missing Skills', f'{len(missing_skills)}']
    ]
    score_table = Table(score_data)
    score_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                                     ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                     ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                     ('FONTSIZE', (0, 0), (-1, 0), 14),
                                     ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                                     ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                                     ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
    story.append(score_table)
    story.append(Spacer(1, 12))
    
    # Skills
    story.append(Paragraph("<b>SKILLS ANALYSIS</b>", styles['Heading2']))
    story.append(Paragraph("<b>Skills Found:</b>", styles['Normal']))
    for skill in found_skills[:10]:
        story.append(Paragraph(f"• {skill}", styles['Normal']))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Missing Skills:</b>", styles['Normal']))
    for skill in missing_skills[:10]:
        story.append(Paragraph(f"• {skill}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Checklist
    story.append(Paragraph("<b>IMPROVEMENT CHECKLIST</b>", styles['Heading2']))
    for item in checklist:
        status_symbol = "✅" if item['status'] == '✅' else "⚠️" if item['status'] == '⚠️' else "❌"
        story.append(Paragraph(f"{status_symbol} {item['item']}", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    
    with open(pdf_file, "rb") as f:
        st.download_button("Download PDF Report", f, file_name=pdf_file, mime="application/pdf")

def dashboard_page():
    if not st.session_state.authenticated:
        st.warning("Please login to view dashboard")
        return
    
    st.markdown('<div class="main-header">Your Dashboard</div>', unsafe_allow_html=True)
    
    conn = sqlite3.connect('resume_analyzer.db')
    
    # Fetch user reports
    reports_df = pd.read_sql_query("SELECT * FROM reports WHERE username=? ORDER BY created_at DESC", 
                                   conn, params=(st.session_state.username,))
    
    if reports_df.empty:
        st.info("No reports found. Upload and analyze your first resume to see analytics!")
        return
    
    # Overview metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Analyses", len(reports_df))
    with col2:
        avg_score = reports_df['resume_score'].mean()
        st.metric("Avg Resume Score", f"{avg_score:.1f}/100")
    with col3:
        best_score = reports_df['resume_score'].max()
        st.metric("Best Resume Score", f"{best_score}/100")
    
    # Score trends
    st.subheader("📈 Score Trends Over Time")
    reports_df['created_at'] = pd.to_datetime(reports_df['created_at'])
    reports_df = reports_df.sort_values('created_at')
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=reports_df['created_at'], y=reports_df['resume_score'], 
                             name='Resume Score', line=dict(color='#4CAF50', width=2)))
    fig.add_trace(go.Scatter(x=reports_df['created_at'], y=reports_df['ats_score'], 
                             name='ATS Score', line=dict(color='#2196F3', width=2)))
    fig.add_trace(go.Scatter(x=reports_df['created_at'], y=reports_df['match_score'], 
                             name='Match Score', line=dict(color='#FF9800', width=2)))
    fig.update_layout(title='Score Progression', xaxis_title='Date', yaxis_title='Score')
    st.plotly_chart(fig, use_container_width=True)
    
    # Recent analyses
    st.subheader("📋 Recent Analyses")
    st.dataframe(reports_df[['created_at', 'role', 'resume_score', 'ats_score']].head(10), 
                 use_container_width=True)
    
    conn.close()

def reports_page():
    st.markdown('<div class="main-header">Report History</div>', unsafe_allow_html=True)
    
    if not st.session_state.authenticated:
        st.warning("Please login to view reports")
        return
    
    conn = sqlite3.connect('resume_analyzer.db')
    reports_df = pd.read_sql_query("SELECT * FROM reports WHERE username=? ORDER BY created_at DESC", 
                                   conn, params=(st.session_state.username,))
    conn.close()
    
    if reports_df.empty:
        st.info("No reports found")
        return
    
    for idx, row in reports_df.iterrows():
        with st.expander(f"📄 Report from {row['created_at']} - {row['role']}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Resume Score", f"{row['resume_score']}/100")
            with col2:
                st.metric("ATS Score", f"{row['ats_score']}/100")
            with col3:
                st.metric("Match Score", f"{row['match_score']:.1f}%")
            
            skills_found = json.loads(row['skills_found'])
            missing_skills = json.loads(row['missing_skills'])
            
            st.write("**Skills Found:**")
            st.write(", ".join(skills_found[:10]))
            st.write("**Missing Skills:**")
            st.write(", ".join(missing_skills[:10]))

def analytics_page():
    st.markdown('<div class="main-header">Admin Analytics</div>', unsafe_allow_html=True)
    
    if st.session_state.username != "admin":
        st.error("Access denied. Admin only.")
        return
    
    conn = sqlite3.connect('resume_analyzer.db')
    
    # Overall statistics
    st.subheader("📊 Platform Analytics")
    
    col1, col2, col3, col4 = st.columns(4)
    users_count = pd.read_sql_query("SELECT COUNT(*) as count FROM users", conn).iloc[0]['count']
    reports_count = pd.read_sql_query("SELECT COUNT(*) as count FROM reports", conn).iloc[0]['count']
    avg_score = pd.read_sql_query("SELECT AVG(resume_score) as avg FROM reports", conn).iloc[0]['avg']
    popular_role = pd.read_sql_query("SELECT role, COUNT(*) as count FROM reports GROUP BY role ORDER BY count DESC LIMIT 1", conn)
    
    with col1:
        st.metric("Total Users", users_count)
    with col2:
        st.metric("Total Reports", reports_count)
    with col3:
        st.metric("Avg Resume Score", f"{avg_score:.1f}/100" if avg_score else "N/A")
    with col4:
        st.metric("Most Popular Role", popular_role.iloc[0]['role'] if not popular_role.empty else "N/A")
    
    # Role distribution
    st.subheader("Job Role Distribution")
    role_dist = pd.read_sql_query("SELECT role, COUNT(*) as count FROM reports GROUP BY role", conn)
    if not role_dist.empty:
        fig = px.pie(role_dist, values='count', names='role', title='Resume Analyses by Role')
        st.plotly_chart(fig, use_container_width=True)
    
    # Daily activity
    st.subheader("Daily Activity")
    daily = pd.read_sql_query("SELECT DATE(created_at) as date, COUNT(*) as count FROM reports GROUP BY DATE(created_at) ORDER BY date DESC LIMIT 30", conn)
    if not daily.empty:
        fig = px.line(daily, x='date', y='count', title='Daily Report Generation')
        st.plotly_chart(fig, use_container_width=True)
    
    # Recent activity
    st.subheader("Recent User Activity")
    recent = pd.read_sql_query("SELECT username, role, resume_score, created_at FROM reports ORDER BY created_at DESC LIMIT 20", conn)
    st.dataframe(recent, use_container_width=True)
    
    conn.close()

def settings_page():
    st.markdown('<div class="main-header">Settings</div>', unsafe_allow_html=True)
    
    st.subheader("Account Information")
    st.write(f"**Username:** {st.session_state.username}")
    
    st.subheader("Notification Preferences")
    email_notifications = st.checkbox("Email notifications for reports")
    weekly_digest = st.checkbox("Weekly analysis digest")
    
    if st.button("Save Preferences"):
        st.success("Preferences saved!")
    
    st.subheader("Account Settings")
    if st.button("Delete All My Data"):
        if st.checkbox("I understand this action is irreversible"):
            conn = sqlite3.connect('resume_analyzer.db')
            c = conn.cursor()
            c.execute("DELETE FROM reports WHERE username=?", (st.session_state.username,))
            c.execute("DELETE FROM resume_history WHERE username=?", (st.session_state.username,))
            conn.commit()
            conn.close()
            st.success("All your data has been deleted!")

if __name__ == "__main__":
    main()