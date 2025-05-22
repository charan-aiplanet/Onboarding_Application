from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import secrets
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
import json
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.llms import OpenAI
from langchain.chains import RetrievalQA
import PyPDF2
import docx
from groq import Groq
import uuid
import pandas as pd
import base64
from fpdf import FPDF
import re
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create directories
DATA_DIR = Path("data")
TEMPLATES_DIR = DATA_DIR / "templates"
EMPLOYEES_DIR = DATA_DIR / "employees"
DOCUMENTS_DIR = DATA_DIR / "documents"

for directory in [DATA_DIR, TEMPLATES_DIR, EMPLOYEES_DIR, DOCUMENTS_DIR, Path(UPLOAD_FOLDER), Path('vectorstores')]:
    directory.mkdir(exist_ok=True, parents=True)

# Email configuration
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'email': 'lukkashivacharan@gmail.com',
    'password': 'trgy ujlb zbdz bupo'
}

# Groq API configuration
GROQ_API_KEY = "your-groq-api-key"
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY != "your-groq-api-key" else None

# Company info from your pre-onboarding app
COMPANY_INFO = {
    "name": "AI Planet",
    "address": "CIE IIIT Hyderabad, Vindhya C4, IIIT-H Campus, Gachibowli, Telangana 500032",
    "website": "www.aiplanet.com",
    "logo_path": "data/logo.png",
    "mission": "Revolutionizing industries through cutting-edge AI solutions",
    "vision": "To be the global leader in enterprise AI implementation and innovation",
    "legal_name": "DPhi Tech Private Limited"
}

# Roles from your pre-onboarding app
ROLES = {
    "Full Stack Developer": {
        "description": "Develop and maintain both frontend and backend components of our applications",
        "skills_required": ["JavaScript", "Python", "React", "Node.js", "MongoDB", "AWS"],
        "onboarding_docs": ["tech_stack.pdf", "coding_standards.pdf", "git_workflow.pdf"],
        "training_modules": ["Frontend Development", "Backend Architecture", "DevOps Basics"]
    },
    "Business Analyst": {
        "description": "Analyze business requirements and translate them into technical specifications",
        "skills_required": ["Data Analysis", "SQL", "Requirements Gathering", "Agile Methodologies"],
        "onboarding_docs": ["business_processes.pdf", "requirement_templates.pdf", "data_analysis_tools.pdf"],
        "training_modules": ["Business Requirements Analysis", "Stakeholder Management", "Agile Project Management"]
    },
    "Data Scientist": {
        "description": "Build and deploy machine learning models to solve complex business problems",
        "skills_required": ["Python", "Machine Learning", "Statistics", "Data Visualization"],
        "onboarding_docs": ["ml_pipelines.pdf", "data_governance.pdf", "model_deployment.pdf"],
        "training_modules": ["Machine Learning Fundamentals", "Model Evaluation", "Production ML Systems"]
    },
    "Product Manager": {
        "description": "Define product vision and roadmap, and work with cross-functional teams to deliver products",
        "skills_required": ["Product Strategy", "Market Research", "User Experience", "Agile/Scrum"],
        "onboarding_docs": ["product_lifecycle.pdf", "roadmap_planning.pdf", "user_research.pdf"],
        "training_modules": ["Product Strategy", "User Research", "Agile Product Management"]
    }
}

# Email template from your pre-onboarding app
OFFER_EMAIL_TEMPLATE = """
Hi {Full_Name},

I am delighted to welcome you to AI Planet as a {Position} and we'd like to extend you an offer to join us. Congratulations!

We are confident that you would play a significant role in driving the vision of AI Planet forward and we look forward to having you onboard for what promises to be a rewarding journey.

The details of your offer letter are in the attached PDF. Please go through the same and feel free to ask if there are any questions.

If all is in order, please sign on all 3 pages of the offer letter (including the last page), and send a scanned copy back as your acceptance latest by {Start_Date}. Also, please check the details such as address or any other relevant details.

I look forward to you joining the team and taking AI Planet to newer heights. If you have any questions, please don't hesitate to reach out to us.

Best regards,  
{HR_Name}
"""

def init_db():
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    
    # Users table for onboarding system
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            designation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Documents table for onboarding system
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            designation TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_by INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uploaded_by) REFERENCES users (id)
        )
    ''')
    
    # Pre-onboarding employees table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            address TEXT,
            position TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            employment_type TEXT NOT NULL,
            location TEXT,
            annual_salary TEXT,
            bonus_details TEXT,
            equity_details TEXT,
            benefits TEXT,
            contingencies TEXT,
            hr_name TEXT,
            offer_sent BOOLEAN DEFAULT 0,
            offer_sent_date TEXT,
            offer_accepted BOOLEAN DEFAULT 0,
            onboarding_completed BOOLEAN DEFAULT 0,
            company_email TEXT,
            initial_password TEXT,
            reporting_manager TEXT,
            manager_email TEXT,
            buddy_name TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Create default admin user
    admin_password = generate_password_hash('aiplanet000')
    cursor.execute('''
        INSERT OR IGNORE INTO users (username, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    ''', ('aiplanet', 'admin@aiplanet.com', admin_password, 'admin'))
    
    conn.commit()
    conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(characters) for _ in range(length))

def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

def clean_for_latin1(text):
    replacements = {
        '\u2013': '-', '\u2014': '-', '\u2018': "'", '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2022': '*', '\u2026': '...',
        '\u00a0': ' ',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode('latin-1', errors='replace').decode('latin-1')

def generate_pdf_offer_letter(candidate_data):
    try:
        print(f"Starting PDF generation for: {candidate_data.get('name', 'Unknown')}")
        
        from fpdf import FPDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        pdf.set_font('Arial', '', 12)
        pdf.set_text_color(0, 0, 0)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Offer Letter with AI Planet', 0, 1, 'C')
    # Add logo at the top right corner on first page - using provided logo
        pdf.image('data/logo.png', x=160, y=10, w=30) if os.path.exists('data/logo.png') else None
    
    # Add date
        pdf.set_font('Arial', '', 12)
        today = datetime.now().strftime("%d %B %Y")
        pdf.cell(0, 10, f'Date: {today}', 0, 1, 'L')
    
    # Add candidate name and address
        pdf.ln(10)
        pdf.set_font('Arial', 'B', 12)
        pdf.set_text_color(0, 0, 150)  # Blue color
        pdf.cell(0, 10, clean_for_latin1(candidate_data["name"]), 0, 1, 'L')
    
        pdf.set_font('Arial', '', 12)
        pdf.set_text_color(0, 0, 0)  # Black color
        pdf.cell(0, 10, f'Address: {candidate_data["address"]}', 0, 1, 'L')
        pdf.cell(0, 10, f'Email: {candidate_data["email"]}', 0, 1, 'L', )
    
    # Letter content
        pdf.ln(10)
        pdf.cell(0, 10, f'Dear {clean_for_latin1(candidate_data["name"])},', 0, 1, 'L')
    
        pdf.ln(5)
        pdf.set_font('Arial', '', 12)
    #content = f'I am delighted & excited to welcome you to AI Planet as a {clean_for_latin1(candidate_data["position"])}. At AI Planet, we believe that our team is our biggest strength and we are looking forward to strengthening it further with your addition. We are confident that you would play a significant role in the overall success of the community that we envision to build and wish you the most enjoyable, learning packed and truly meaningful experience with AI Planet.'
    #pdf.multi_cell(0, 6, clean_for_latin1(content))
        pdf.set_font('Arial', '', 12); pdf.write(6, clean_for_latin1('I am delighted & excited to welcome you to AI Planet as a ')); pdf.set_font('Arial', 'B', 12); pdf.write(6, clean_for_latin1(candidate_data["position"])); pdf.set_font('Arial', '', 12); pdf.write(6, clean_for_latin1('. At AI Planet, we believe that our team is our biggest strength and we are looking forward to strengthening it further with your addition. We are confident that you would play a significant role in the overall success of the community that we envision to build and wish you the most enjoyable, learning packed and truly meaningful experience with AI Planet.'))
        pdf.ln(10)
        pdf.write(6, 'Your appointment will be governed by the terms and conditions presented in ');  pdf.set_font('Arial', 'B', 12) ;pdf.write(6, 'Annexure A.') ;pdf.set_font('Arial', '', 12); 
    
        pdf.ln(10)
        pdf.multi_cell(0, 6, 'We look forward to you joining us. Please do not hesitate to call us for any information you may need. Also, please sign the duplicate of this offer as your acceptance and forward the same to us.')
    
        pdf.ln(10)
        pdf.cell(0, 10, 'Congratulations!', 0, 1, 'L')
    
        pdf.image('data/chanukya-sign.png') if os.path.exists('data/chanukya-sign.png') else None
        pdf.cell(0, 10, 'Chanukya Patnaik', 0, 1, 'L')
        pdf.cell(0, 6, 'Founder, AI Planet (DPhi)', 0, 1, 'L')
    
    # Company footer
        pdf.ln(40)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 5, clean_for_latin1(f'{COMPANY_INFO["legal_name"]} | {COMPANY_INFO["address"]}'))
    
    # Annexure A - Page 2
        pdf.add_page()

    #pdf.set_font('Arial', 'Offer letter with AI Planet', 12)
    # Add logo at the top right corner on second page
        pdf.image('logo.png', x=160, y=10, w=30) if os.path.exists('logo.png') else None
    
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(0, 0, 150)  # Blue colordata\logo.png
        pdf.cell(0, 15, 'Annexure A', 0, 1, 'L')
    
        pdf.set_font('Arial', '', 12)
        pdf.set_text_color(0, 0, 0)  # Black color
        pdf.multi_cell(0, 6, 'You shall be governed by the following terms and conditions of service during your engagement with AI Planet, and those may be amended from time to time.')
    
        pdf.ln(5)
    # Numbered points - clean each point for latin1 encoding
        points = [
        f'You will be working with AI Planet as a {clean_for_latin1(candidate_data["position"])}. You would be responsible for aspects related to conducting market research to identify trends and AI use cases, support the sales team by qualifying leads, preparing tailored presentations, and building strong customer relationships. Additionally, you will be playing an important role in realizing the design, planning, development, and deployment platforms/solutions. Further, it may also require you to do various roles and go that extra mile in the best interest of the product.',
        f'Your date of joining is {clean_for_latin1(candidate_data["start_date"])}. During your employment, we expected to devote your time and efforts solely to AI Planet work. You are also required to let your mentor know about forthcoming events (if there are any) in advance so that your work can be planned accordingly.',
        f'You will be working onsite in our Hyderabad office on all working days. There will be catch ups scheduled with your mentor to discuss work progress and overall work experience at regular intervals.',
        f'All the work that you will produce at or in relation to AI Planet will be the intellectual property of AI Planet. You are not allowed to store, copy, sell, share, and distribute it to a third party under any circumstances. Similarly, you are expected to refrain from talking about your work in public domains (both online such as blogging, social networking sites and offline among your friends, college etc.) without prior discussion and approval with your mentor.',
        f'We take data privacy and security very seriously and to maintain confidentiality of any students, customers, clients, and companies\' data and contact details that you may get access to during your engagement will be your responsibility. AI Planet operates on zero tolerance principle with regards to any breach of data security guidelines. At the completion of the engagement, you are expected to hand over all AI Planet work/data stored on your Personal Computer to your mentor and delete the same from your machine.',
        f'Under normal circumstances either the company or you may terminate this association by providing a notice of 30 days without assigning any reason. However, the company may terminate this agreement forthwith under situations of in-disciplinary behaviors.',
        f'During the appointment period you shall not engage yourselves directly or indirectly or in any capacity in any other organization (other than your college).'
        f'You are expected to conduct yourself with utmost professionalism in dealing with your mentor, team members, colleagues, clients and customers and treat everyone with due respect.',
        
        ]
    
    # Process each point to ensure it's clean for latin1 encoding
        points = [clean_for_latin1(point) for point in points]
    # Process each point to ensure it's clean for latin1 encoding and properly format bold text
        pdf.ln(5)
        for i, point in enumerate(points, 1):
            if i > 7:  # Add remaining points to page 3
                break
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(8, 6, f'{i}.', 0, 0)
            pdf.set_font('Arial', '', 12)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.multi_cell(180, 6, point)
            pdf.ln(5)
    
    # Company footer
        pdf.ln(10)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 5, clean_for_latin1(f'{COMPANY_INFO["legal_name"]} | {COMPANY_INFO["address"]}'))
    
    # Page 3 with remaining points
        pdf.add_page()
    
    
    # Add logo at the top right corner on third page
        pdf.image('logo.png', x=160, y=10, w=30) if os.path.exists('logo.png') else None
        pdf.ln(15)
    # Continue with remaining points
        for i, point in enumerate(points[8:], 8):
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(8, 6, f'{i}.', 12, 12)
            pdf.set_font('Arial', '', 12)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.multi_cell(180, 6, point)
            pdf.ln(5)
    
    # Additional points
        extra_points = [
        f'AI Planet is a start-up and we love people who like to go beyond the normal call of duty and can think out of the box. Surprise us with your passion, intelligence, creativity, and hard work – and expect appreciation & rewards to follow.',
        f'Expect constant and continuous objective feedback from your mentor and other team members and we encourage you to ask for and provide feedback at every possible opportunity. It is your right to receive and give feedback – this is the ONLY way we all can continuously push ourselves to do better.',
        f'Have fun at what you do and do the right thing – both the principles are core of what AI Planet stands for and we expect you to imbibe them in your day to day actions and continuously challenge us if we are falling short of expectations on either of them.',
        f'You will be provided INR {clean_for_latin1(candidate_data["annual_salary"])} /- per month as a salary. Post three months you will be considered for ESOPs. ESOPs are based on a four-year vesting schedule with a one-year cliff.'
        ]
    
    # Process each extra point to ensure it's clean for latin1 encoding
        extra_points = [clean_for_latin1(point) for point in extra_points]
    
        for i, point in enumerate(extra_points, len(points) + 1):
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(8, 6, f'{i}.', 0, 0)
            pdf.set_font('Arial', '', 12)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.multi_cell(180, 6, point)
            pdf.ln(5)
    
    # Signature section
        pdf.ln(5)
        pdf.set_font('Arial', '', 12)
        pdf.multi_cell(0, 6, 'I have negotiated, agreed, read and understood all the terms and conditions of this engagement letter as well as Annexure hereto and affix my signature in complete acceptance of the terms of the letter.')
    
        pdf.ln(10)
        pdf.cell(50, 10, 'Date: ________________', 0, 0, 'L')
        pdf.cell(0, 10, 'Signature: ________________', 0, 1, 'L')
    
        pdf.ln(5)
        pdf.cell(50, 10, 'Place: ________________', 0, 0, 'L')
        pdf.cell(0, 10, 'Name: ________________', 0, 1, 'L')
    
    # Company footer
        pdf.ln(90)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 5, clean_for_latin1(f'{COMPANY_INFO["legal_name"]} | {COMPANY_INFO["address"]}'))
        # Header
                # Generate PDF as bytes
        pdf_bytes = pdf.output(dest='S')
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode('latin-1')
        
        # Save to file
        sanitized_name = re.sub(r'[^\w\s-]', '', candidate_data.get("name", "candidate")).strip().replace(' ', '_')
        today_str = datetime.now().strftime("%Y%m%d")
        filename = f"{sanitized_name}_{today_str}_offer_letter.pdf"
        file_path = DOCUMENTS_DIR / filename
        
        with open(str(file_path), 'wb') as f:
            f.write(pdf_bytes)
        
        print(f"PDF saved to: {file_path}")
        
        # Return base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        print(f"PDF generated successfully, base64 length: {len(pdf_base64)}")
        
        return pdf_base64
        
    except Exception as e:
        print(f"Error in PDF generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def send_email(to_email, subject, content, attachments=None, pdf_content=None, sender_name=None):
    try:
        print(f"=== EMAIL SENDING DEBUG ===")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"PDF Content provided: {pdf_content is not None}")
        if pdf_content:
            print(f"PDF Content length: {len(pdf_content)}")
            print(f"PDF Content first 50 chars: {pdf_content[:50]}...")
        
        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG['email']
        msg["To"] = to_email
        msg["Subject"] = subject
        
        # Add text content
        msg.attach(MIMEText(content, "plain"))
        print("Email text content attached")

        # Add PDF attachment if provided
        if pdf_content:
            try:
                print("Processing PDF attachment...")
                
                # Ensure we have clean base64 data
                pdf_content_clean = pdf_content.strip()
                
                # Decode base64 to bytes
                pdf_bytes = base64.b64decode(pdf_content_clean)
                print(f"PDF decoded successfully, byte length: {len(pdf_bytes)}")
                
                # Verify it's a valid PDF by checking header
                if pdf_bytes[:4] == b'%PDF':
                    print("Valid PDF header detected")
                else:
                    print(f"Warning: PDF header not found. First 10 bytes: {pdf_bytes[:10]}")
                
                # Create attachment
                attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
                attachment.add_header(
                    "Content-Disposition", 
                    "attachment", 
                    filename="AI_Planet_Offer_Letter.pdf"
                )
                msg.attach(attachment)
                print("PDF attachment successfully added to email")
                
            except Exception as pdf_error:
                print(f"Error processing PDF attachment: {pdf_error}")
                print("Continuing to send email without attachment...")

        # Send email
        print("Connecting to SMTP server...")
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            print("SMTP connection established, logging in...")
            server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
            print("SMTP login successful, sending message...")
            
            # Convert message to string for sending
            text = msg.as_string()
            server.sendmail(EMAIL_CONFIG['email'], to_email, text)
            print("Email sent successfully!")
        
        print("=== EMAIL SENDING COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"=== EMAIL SENDING FAILED ===")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print("=== END EMAIL ERROR ===")
        return False

def send_employee_credentials_email(employee_email, employee_name, password, designation):
    """Send credentials email to new employee"""
    try:
        subject = f"Welcome to AI Planet - Your Login Credentials"
        
        email_body = f"""
Dear {employee_name},

Welcome to AI Planet! We're excited to have you join our team.

Your onboarding account has been created. Please find your login credentials below:

Email: {employee_email}
Temporary Password: {password}
Designation: {designation}

Please log in to our onboarding portal at your earliest convenience to:
- Access your role-specific documents
- Complete your onboarding process
- Get assistance from our AI chatbot

For security reasons, we recommend changing your password after your first login.

If you have any questions, please don't hesitate to contact our HR team.

Best regards,
AI Planet HR Team

---
This is an automated message from AI Planet Onboarding System.
"""
        
        return send_email(employee_email, subject, email_body)
    except Exception as e:
        print(f"Failed to send credentials email: {e}")
        return False

# Database functions for employees (pre-onboarding)
def get_employees():
    conn = sqlite3.connect('onboarding.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_employee_by_id(employee_id):
    conn = sqlite3.connect('onboarding.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees WHERE id = ?", (employee_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def save_employee(employee_data):
    conn = sqlite3.connect('onboarding.db')
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM employees WHERE id = ?", (employee_data["id"],))
    exists = cur.fetchone()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not exists:
        employee_data["created_at"] = now
        employee_data["updated_at"] = now
        columns = list(employee_data.keys())
        placeholders = ["?"] * len(columns)
        values = [employee_data[col] for col in columns]
        query = f"INSERT INTO employees ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        cur.execute(query, values)
    else:
        employee_data["updated_at"] = now
        set_items = [f"{col} = ?" for col in employee_data.keys() if col != "id"]
        values = [employee_data[col] for col in employee_data.keys() if col != "id"]
        values.append(employee_data["id"])
        query = f"UPDATE employees SET {', '.join(set_items)} WHERE id = ?"
        cur.execute(query, values)
    
    conn.commit()
    conn.close()

# Functions for chatbot and document management
def extract_text_from_file(file_path):
    text = ""
    file_ext = file_path.split('.')[-1].lower()
    
    if file_ext == 'pdf':
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
    elif file_ext == 'docx':
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    elif file_ext == 'txt':
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
    
    return text

def create_vector_store(designation):
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM documents WHERE designation = ?', (designation,))
    files = cursor.fetchall()
    conn.close()
    
    if not files:
        return None
    
    documents = []
    for file_path in files:
        text = extract_text_from_file(file_path[0])
        if text.strip():
            documents.append(text)
    
    if not documents:
        return None
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    texts = text_splitter.split_text('\n'.join(documents))
    
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = FAISS.from_texts(texts, embeddings)
    
    vectorstore_path = f"vectorstores/{designation}"
    vectorstore.save_local(vectorstore_path)
    
    return vectorstore

def get_chatbot_response(question, designation):
    try:
        vectorstore_path = f"vectorstores/{designation}"
        if not os.path.exists(vectorstore_path):
            create_vector_store(designation)
        
        if os.path.exists(vectorstore_path) and groq_client:
            embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            vectorstore = FAISS.load_local(vectorstore_path, embeddings, allow_dangerous_deserialization=True)
            
            relevant_docs = vectorstore.similarity_search(question, k=3)
            context = "\n".join([doc.page_content for doc in relevant_docs])
            
            prompt = f"""
            Based on the following context from onboarding documents, please answer the question.
            If the answer is not found in the context, please say so politely.
            
            Context: {context}
            
            Question: {question}
            
            Answer:
            """
            
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                max_tokens=500,
                temperature=0.3
            )
            
            return response.choices[0].message.content
        else:
            return "I don't have access to documents for your designation yet. Please contact your administrator."
    
    except Exception as e:
        return f"I'm sorry, I encountered an error: {str(e)}"

@app.route('/')
def index():
    if 'user_id' not in session:
        return render_template('login.html')
    
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    cursor.execute('SELECT role, designation FROM users WHERE id = ?', (session['user_id'],))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data[0] == 'admin':
        return render_template('admin_dashboard.html')
    else:
        return render_template('employee_dashboard.html', designation=user_data[1])

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash, role, designation FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user[1], password):
        session['user_id'] = user[0]
        session['role'] = user[2]
        if user[3]:
            session['designation'] = user[3]
        return jsonify({'success': True, 'role': user[2]})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/preonboarding')
def preonboarding():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    return render_template('preonboarding.html')

# Pre-onboarding API endpoints
@app.route('/api/employees', methods=['GET'])
def api_get_employees():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    employees = get_employees()
    return jsonify(employees)

@app.route('/api/employees', methods=['POST'])
def api_create_employee():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['name', 'email', 'position', 'start_date']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Validate email format
        if not is_valid_email(data.get('email', '')):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        employee_id = str(uuid.uuid4())
        
        employee_data = {
            "id": employee_id,
            "name": data.get('name'),
            "email": data.get('email'),
            "address": data.get('address', ''),
            "position": data.get('position'),
            "start_date": data.get('start_date'),
            "end_date": data.get('end_date'),
            "employment_type": data.get('employment_type', 'Full-time'),
            "location": data.get('location', 'AI Planet HQ, Hyderabad'),
            "annual_salary": str(data.get('annual_salary', '0')),
            "bonus_details": data.get('bonus_details', ''),
            "equity_details": data.get('equity_details', ''),
            "benefits": data.get('benefits', ''),
            "contingencies": data.get('contingencies', ''),
            "hr_name": data.get('hr_name', 'Eswar Viswanathan'),
            "reporting_manager": data.get('reporting_manager', 'Chanukya Patnaik'),
            "offer_sent": False,
            "offer_accepted": False,
            "onboarding_completed": False
        }
        
        save_employee(employee_data)
        return jsonify({'success': True, 'id': employee_id, 'message': 'Employee created successfully'})
        
    except Exception as e:
        print(f"Error creating employee: {e}")
        return jsonify({'success': False, 'error': 'Failed to create employee'}), 500

@app.route('/api/employees/<employee_id>/offer_letter', methods=['POST'])
def api_generate_offer_letter(employee_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    employee = get_employee_by_id(employee_id)
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404
    
    pdf_content = generate_pdf_offer_letter(employee)
    return jsonify({'success': True, 'pdf_content': pdf_content})

@app.route('/api/employees/<employee_id>/send_offer', methods=['POST'])
def api_send_offer(employee_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    employee = get_employee_by_id(employee_id)
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404
    
    # Generate PDF
    pdf_content = generate_pdf_offer_letter(employee)
    
    # Format email content
    email_content = OFFER_EMAIL_TEMPLATE.format(
        Full_Name=employee["name"],
        Position=employee["position"],
        Start_Date=employee["start_date"],
        HR_Name=employee["hr_name"]
    )
    
    subject = f"Job Offer: {employee['position']} at AI Planet"
    
    # Send email
    if send_email(employee["email"], subject, email_content, pdf_content=pdf_content):
        # Update employee status
        employee["offer_sent"] = True
        employee["offer_sent_date"] = datetime.now().strftime("%Y-%m-%d")
        save_employee(employee)
        
        return jsonify({'success': True, 'message': 'Offer letter sent successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send email'})

@app.route('/api/employees/<employee_id>', methods=['PUT'])
def api_update_employee(employee_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    employee = get_employee_by_id(employee_id)
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404
    
    data = request.json
    
    # Update employee data
    for key, value in data.items():
        if key in employee:
            employee[key] = value
    
    save_employee(employee)
    return jsonify({'success': True})

@app.route('/api/test_pdf/<employee_id>')
def test_pdf_generation(employee_id):
    """Test endpoint to verify PDF generation"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        employee = get_employee_by_id(employee_id)
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404
        
        print(f"Testing PDF generation for: {employee}")
        
        # Generate PDF
        pdf_content = generate_pdf_offer_letter(employee)
        
        if pdf_content:
            return jsonify({
                'success': True,
                'pdf_length': len(pdf_content),
                'employee_name': employee.get('name'),
                'pdf_preview': pdf_content[:100] + '...' if len(pdf_content) > 100 else pdf_content
            })
        else:
            return jsonify({'success': False, 'error': 'PDF generation failed'})
            
    except Exception as e:
        print(f"Test PDF error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Add route to serve generated PDFs directly
@app.route('/api/employees/<employee_id>/download_pdf')
def download_employee_pdf(employee_id):
    """Direct download endpoint for generated PDFs"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        employee = get_employee_by_id(employee_id)
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404
        
        # Check if PDF exists in documents directory
        sanitized_name = re.sub(r'[^\w\s-]', '', employee.get("name", "candidate")).strip().replace(' ', '_')
        today_str = datetime.now().strftime("%Y%m%d")
        filename = f"{sanitized_name}_{today_str}_offer_letter.pdf"
        file_path = DOCUMENTS_DIR / filename
        
        if os.path.exists(file_path):
            return send_file(str(file_path), as_attachment=True, download_name=f"AI_Planet_{employee.get('name', 'candidate')}_Offer_Letter.pdf")
        else:
            # Generate new PDF if not exists
            pdf_content = generate_pdf_offer_letter(employee)
            if pdf_content:
                # Convert base64 to bytes and send
                pdf_bytes = base64.b64decode(pdf_content)
                from io import BytesIO
                pdf_io = BytesIO(pdf_bytes)
                pdf_io.seek(0)
                
                return send_file(
                    pdf_io,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f"AI_Planet_{employee.get('name', 'candidate')}_Offer_Letter.pdf"
                )
            else:
                return jsonify({'error': 'Failed to generate PDF'}), 500
                
    except Exception as e:
        print(f"Download PDF error: {e}")
        return jsonify({'error': str(e)}), 500

# Onboarding system endpoints (keeping existing ones)
@app.route('/create_user', methods=['POST'])
@app.route('/create_user', methods=['POST'])
def create_user():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    data = request.json
    full_name = data['full_name']
    email = data['email']
    designation = data['designation']
    
    password = generate_password()
    password_hash = generate_password_hash(password)
    
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role, designation)
            VALUES (?, ?, ?, ?, ?)
        ''', (full_name, email, password_hash, 'employee', designation))
        conn.commit()
        
        # Actually send the email using your existing function
        email_sent = send_employee_credentials_email(email, full_name, password, designation)
        
        if email_sent:
            return jsonify({'success': True, 'message': 'User created and credentials sent successfully'})
        else:
            return jsonify({'success': True, 'message': 'User created but email failed to send. Please contact the user manually.'})
            
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already exists'})
    finally:
        conn.close()
        
        
@app.route('/upload_document', methods=['POST'])
def upload_document():
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file selected'})
    
    file = request.files['file']
    designation = request.form['designation']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
        filename = timestamp + filename
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        conn = sqlite3.connect('onboarding.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO documents (filename, designation, file_path, uploaded_by)
            VALUES (?, ?, ?, ?)
        ''', (filename, designation, file_path, session['user_id']))
        conn.commit()
        conn.close()
        
        create_vector_store(designation)
        
        return jsonify({'success': True, 'message': 'Document uploaded successfully'})
    else:
        return jsonify({'success': False, 'message': 'Invalid file type'})

@app.route('/get_documents')
def get_documents():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    
    if session.get('role') == 'admin':
        cursor.execute('SELECT filename, designation, uploaded_at FROM documents ORDER BY uploaded_at DESC')
    else:
        cursor.execute('SELECT designation FROM users WHERE id = ?', (session['user_id'],))
        designation = cursor.fetchone()[0]
        cursor.execute('SELECT filename, designation, uploaded_at FROM documents WHERE designation = ? ORDER BY uploaded_at DESC', (designation,))
    
    documents = cursor.fetchall()
    conn.close()
    
    return jsonify({'success': True, 'documents': documents})

@app.route('/download_document/<filename>')
def download_document(filename):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        flash('File not found')
        return redirect(url_for('index'))

@app.route('/chatbot', methods=['POST'])
def chatbot():
    if 'user_id' not in session or session.get('role') != 'employee':
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    question = request.json.get('question')
    
    conn = sqlite3.connect('onboarding.db')
    cursor = conn.cursor()
    cursor.execute('SELECT designation FROM users WHERE id = ?', (session['user_id'],))
    designation = cursor.fetchone()[0]
    conn.close()
    
    response = get_chatbot_response(question, designation)
    return jsonify({'success': True, 'response': response})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
    app.run(debug=True, host='0.0.0.0', port=5000)