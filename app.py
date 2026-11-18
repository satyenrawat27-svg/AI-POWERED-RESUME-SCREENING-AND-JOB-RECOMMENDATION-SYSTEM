from collections import Counter
from flask import send_file
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from  reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
import sqlite3
import json
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-development-only-key"
)
# Database file location
DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database.db"
)


# Create database and table
# Create database and tables


def init_db():

    with sqlite3.connect(DATABASE) as conn:

        # Resume analysis table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_filename TEXT NOT NULL,
                skills_json TEXT NOT NULL,
                recommendations_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check resume table columns
        resume_columns = [
            row[1] for row in conn.execute(
                "PRAGMA table_info(resume_analyses)"
            ).fetchall()
        ]

        # Add user_id if missing
        if "user_id" not in resume_columns:
            conn.execute("""
                ALTER TABLE resume_analyses
                ADD COLUMN user_id INTEGER
            """)

        # Check users table columns
        user_columns = [
            row[1] for row in conn.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        ]

        # Add role if missing
        if "role" not in user_columns:
            conn.execute("""
                ALTER TABLE users
                ADD COLUMN role TEXT NOT NULL DEFAULT 'user'
            """)

        # Save database changes
        conn.commit()


# Save resume analysis

def save_analysis(user_id, filename, skills, recommendations):

    with sqlite3.connect(DATABASE) as conn:

        conn.execute("""
            INSERT INTO resume_analyses
            (user_id, resume_filename, skills_json,
             recommendations_json)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            filename,
            json.dumps(skills),
            json.dumps(recommendations)
        ))

        conn.commit()



# Create database automatically
init_db()


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

SKILLS_LIST = [
    "Python", "Java", "SQL", "HTML", "CSS",
    "JavaScript", "Flask", "Django",
    "Machine Learning", "Data Analysis",
    "C++", "Excel", "React", "PHP",
    "MySQL", "MongoDB", "AWS", "Git"
]

# Sample job dataset for the project
JOBS = [
    {
        "title": "Python Developer",
        "skills": ["Python", "Flask", "SQL", "Git"],
        "description": "Python Flask SQL Git backend development"
    },
    {
        "title": "Web Developer",
        "skills": ["HTML", "CSS", "JavaScript", "React"],
        "description": "HTML CSS JavaScript React frontend web development"
    },
    {
        "title": "Data Analyst",
        "skills": ["Python", "SQL", "Excel", "Data Analysis"],
        "description": "Python SQL Excel Data Analysis reports"
    },
    {
        "title": "Machine Learning Engineer",
        "skills": ["Python", "Machine Learning", "SQL"],
        "description": "Python Machine Learning SQL artificial intelligence"
    },
    {
        "title": "Java Developer",
        "skills": ["Java", "SQL", "MySQL", "Git"],
        "description": "Java SQL MySQL Git software development"
    }
]

# Create and initialize Jobs Database Table

def init_job_db():

    with sqlite3.connect(DATABASE) as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                skills_json TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add existing sample jobs only if table is empty
        count = conn.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0]

        if count == 0:

            for job in JOBS:

                conn.execute("""
                    INSERT INTO jobs
                    (title, skills_json, description)
                    VALUES (?, ?, ?)
                """, (
                    job["title"],
                    json.dumps(job["skills"]),
                    job["description"]
                ))

        conn.commit()


# Read jobs from database
def get_jobs():

    with sqlite3.connect(DATABASE) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
        
            SELECT * FROM jobs
            ORDER BY id DESC
        """).fetchall()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "skills": json.loads(row["skills_json"]),
            "description": row["description"]
        }
        for row in rows
    ]


# Initialize jobs table
init_job_db()


def find_skills(resume_text):
    found_skills = []
    resume_lower = resume_text.lower()

    for skill in SKILLS_LIST:
        if skill.lower() in resume_lower:
            found_skills.append(skill)

    return found_skills


def recommend_jobs(resume_text, found_skills):

    recommendations = []

    # Normalize detected skills
    detected = {
        skill.strip().casefold()
        for skill in found_skills
    }

    for job in get_jobs():

        # Find matching skills
        matched = [
            skill for skill in job["skills"]
            if skill.strip().casefold() in detected
        ]

        # Find missing skills
        missing = [
            skill for skill in job["skills"]
            if skill.strip().casefold() not in detected
        ]

        # Calculate percentage
        total_skills = len(job["skills"])

        score = (
            len(matched) / total_skills * 100
            if total_skills > 0 else 0
        )

        recommendations.append({
            "title": job["title"],
            "score": round(score, 2),
            "matched_skills": matched,
            "missing_skills": missing
        })

    # Sort highest score first
    recommendations.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return recommendations



@app.route("/", methods=["GET", "POST"])
def home():
    message = ""
    resume_text = ""
    found_skills = []
    recommended_jobs = []

    if request.method == "POST":

        if "user_id" not in session:
            return redirect(url_for("login"))

    file = request.files.get("resume")
    if not file or file.filename == "":
            message = "Please select a PDF resume."

    elif not file.filename.lower().endswith(".pdf"):
            message = "Only PDF files are allowed."

    else:
            filename = secure_filename(file.filename)

            if not filename:
                message = "Invalid file name."

            else:
                filepath = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )

                try:

                
                    file.save(filepath)

                    reader = PdfReader(filepath)

                    if reader.is_encrypted:
                        result = reader.decrypt("")

                        if result == 0:
                            raise ValueError("PDF is password protected.")

                    resume_text = "\n".join(
                          
                         page.extract_text() or ""
                         for page in reader.pages
                    )

                    print("PDF pages:", len(reader.pages))
                    print("Extracted text length:", len(resume_text))

                    if not resume_text.strip():
                        message = (
                            "No readable text found. "
                            "Please upload a text-based PDF."
                        )
                    else:
                        found_skills = find_skills(resume_text)
                        print("DETECTED SKILLS:", found_skills)
                        recommended_jobs = recommend_jobs(
                            resume_text,
                            found_skills
                        )
                        save_analysis(
                            session["user_id"],
                            filename,
                            found_skills,
                            recommended_jobs
                        )

                        message = "Resume analyzed successfully!"

                except Exception as e:
                    print("PDF ERROR:", repr(e))

                    message = (
                         "PDF could not be read. "
                         "Please try another PDF."
                    )    

                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)

    return render_template(
        "index.html",
        message=message,
        resume_text=resume_text,
        found_skills=found_skills,
        recommended_jobs=recommended_jobs
    )



@app.route("/register", methods=["GET", "POST"])
def register():

    message = ""
    success = False

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password", ""
        )

        if not name or not email or not password:
            message = "Please fill in all required fields."

        elif len(password) < 8:
            message = "Password must be at least 8 characters."

        elif password != confirm_password:
            message = "Passwords do not match."

        else:
            password_hash = generate_password_hash(password)

            try:
                with sqlite3.connect(DATABASE) as conn:

                    conn.execute("""
                        INSERT INTO users
                        (name, email, password_hash)
                        VALUES (?, ?, ?)
                    """, (
                        name,
                        email,
                        password_hash
                    ))

                    conn.commit()

                message = "Account created successfully!"
                success = True

            except sqlite3.IntegrityError:
                message = "This email is already registered."

    return render_template(
        "register.html",
        message=message,
        success=success
    )
@app.route("/login", methods=["GET", "POST"])
def login():

    message = ""

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with sqlite3.connect(DATABASE) as conn:
            conn.row_factory = sqlite3.Row

            user = conn.execute("""
                SELECT id, name, email, password_hash , role
                FROM users
                WHERE email = ?
            """, (email,)).fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]

# Admin and normal user redirect
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("dashboard"))


        else:
            message = "Invalid email or password."

    return render_template(
        "login.html",
        message=message
    )


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        name=session.get("user_name")
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))
@app.route("/history")
def history():

    # Login check
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Get only the logged-in user's history
    with sqlite3.connect(DATABASE) as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT * FROM resume_analyses
            WHERE user_id = ?
            ORDER BY id DESC
        """, (session["user_id"],)).fetchall()

    analyses = []

    for row in rows:

        analyses.append({
            "id": row["id"],
            "resume_filename": row["resume_filename"],
            "skills": json.loads(row["skills_json"]),
            "recommendations": json.loads(
                row["recommendations_json"]
            ),
            "created_at": row["created_at"]
        })

    return render_template(
        "history.html",
        analyses=analyses
    )

@app.route("/admin")
def admin_dashboard():

    # Check login
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only admin can access this page
    if session.get("user_role") != "admin":
        return redirect(url_for("dashboard"))

    with sqlite3.connect(DATABASE) as conn:

        conn.row_factory = sqlite3.Row

        # Total registered users
        total_users = conn.execute("""
            SELECT COUNT(*) FROM users
        """).fetchone()[0]

        # Total uploaded resumes
        total_resumes = conn.execute("""
            SELECT COUNT(*) FROM resume_analyses
        """).fetchone()[0]

        # Fetch all recommendation data
        recommendation_rows = conn.execute("""
            SELECT recommendations_json
            FROM resume_analyses
        """).fetchall()

        total_recommendations = 0

        for row in recommendation_rows:
            try:
                jobs = json.loads(row["recommendations_json"])
                total_recommendations += len(jobs)
            except (json.JSONDecodeError, TypeError):
                continue

        # Recent resume analyses
        recent_analyses = conn.execute("""
            SELECT
                resume_analyses.id,
                resume_analyses.resume_filename,
                resume_analyses.created_at,
                users.name
            FROM resume_analyses
            LEFT JOIN users
            ON resume_analyses.user_id = users.id
            ORDER BY resume_analyses.id DESC
            LIMIT 10
        """).fetchall()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_resumes=total_resumes,
        total_recommendations=total_recommendations,
        recent_analyses=recent_analyses
    )
@app.route("/admin/users")
def admin_users():

    # Check whether user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Only admin can access this page
    if session.get("user_role") != "admin":
        return redirect(url_for("dashboard"))

    with sqlite3.connect(DATABASE) as conn:

        conn.row_factory = sqlite3.Row

        users = conn.execute("""
            SELECT id, name, email, role, created_at
            FROM users
            ORDER BY id DESC
        """).fetchall()

    return render_template(
        "admin_users.html",
        users=users
    )


# Admin Job Management Route

@app.route("/admin/jobs", methods=["GET", "POST"])
def admin_jobs():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "admin":
        return redirect(url_for("dashboard"))

    message = ""

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        skills_text = request.form.get("skills", "").strip()
        description = request.form.get("description", "").strip()

        skills = [
            skill.strip()
            for skill in skills_text.split(",")
            if skill.strip()
        ]

        if not title or not skills or not description:

            message = "Please fill in all fields."

        else:

            with sqlite3.connect(DATABASE) as conn:

                conn.execute("""
                    INSERT INTO jobs
                    (title, skills_json, description)
                    VALUES (?, ?, ?)
                """, (
                    title,
                    json.dumps(skills),
                    description
                ))

                conn.commit()

            message = "Job added successfully!"

    with sqlite3.connect(DATABASE) as conn:

        conn.row_factory = sqlite3.Row

        jobs = conn.execute("""
            SELECT * FROM jobs
            ORDER BY id DESC
        """).fetchall()

    return render_template(
        "admin_jobs.html",
        jobs=jobs,
        message=message
    )

# Edit Existing Job

@app.route("/admin/jobs/edit/<int:job_id>", methods=["GET", "POST"])
def edit_job(job_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "admin":
        return redirect(url_for("dashboard"))

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row

        job = conn.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,)
        ).fetchone()

    if job is None:
        return redirect(url_for("admin_jobs"))

    title_value = job["title"]
    skills_value = ", ".join(json.loads(job["skills_json"]))
    description_value = job["description"]

    message = ""

    if request.method == "POST":

        title_value = request.form.get("title", "").strip()
        skills_value = request.form.get("skills", "").strip()
        description_value = request.form.get(
            "description", ""
        ).strip()

        skills = [
            skill.strip()
            for skill in skills_value.split(",")
            if skill.strip()
        ]

        if not title_value or not skills or not description_value:

            message = "Please fill in all fields."

        else:

            with sqlite3.connect(DATABASE) as conn:

                conn.execute("""
                    UPDATE jobs
                    SET title = ?,
                        skills_json = ?,
                        description = ?
                    WHERE id = ?
                """, (
                    title_value,
                    json.dumps(skills),
                    description_value,
                    job_id
                ))

                conn.commit()

            return redirect(url_for("admin_jobs"))

    return render_template(
        "edit_job.html",
        job=job,
        title=title_value,
        skills=skills_value,
        description=description_value,
        message=message
    )


# Delete Job Route

@app.route(
    "/admin/jobs/delete/<int:job_id>",
    methods=["POST"]
)
def delete_job(job_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_role") != "admin":
        return redirect(url_for("dashboard"))

    with sqlite3.connect(DATABASE) as conn:

        conn.execute(
            "DELETE FROM jobs WHERE id = ?",
            (job_id,)
        )

        conn.commit()

    return redirect(url_for("admin_jobs"))

@app.route("/download-report/<int:analysis_id>")
def download_report(analysis_id):

    # User must be logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Fetch only the logged-in user's analysis
    with sqlite3.connect(DATABASE) as conn:

        conn.row_factory = sqlite3.Row

        record = conn.execute("""
            SELECT *
            FROM resume_analyses
            WHERE id = ? AND user_id = ?
        """, (
            analysis_id,
            session["user_id"]
        )).fetchone()

    if record is None:
        return "Report not found or access denied.", 404

    # Read stored JSON data
    try:
        skills = json.loads(record["skills_json"])
        recommendations = json.loads(
            record["recommendations_json"]
        )
    except (json.JSONDecodeError, TypeError):
        return "Invalid analysis data.", 500

    # Create PDF in memory
    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    story = []

    # Report title
    story.append(
        Paragraph(
            "SmartHire AI - Resume Analysis Report",
            styles["Title"]
        )
    )

    story.append(Spacer(1, 20))

    # Resume information
    story.append(
        Paragraph(
            "<b>Resume File:</b> " +
            escape(str(record["resume_filename"])),
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "<b>Analysis Date:</b> " +
            escape(str(record["created_at"])),
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 20))

    # Detected skills
    story.append(
        Paragraph("Detected Skills", styles["Heading2"])
    )

    if skills:
        skills_text = ", ".join(
            escape(str(skill)) for skill in skills
        )
    else:
        skills_text = "No skills detected."

    story.append(
        Paragraph(skills_text, styles["Normal"])
    )

    story.append(Spacer(1, 20))

    # Job recommendations
    story.append(
        Paragraph(
            "Recommended Jobs",
            styles["Heading2"]
        )
    )

    header_style = ParagraphStyle(
        "ReportHeader",
        parent=styles["Normal"],
        textColor=colors.white,
        fontName="Helvetica-Bold",
        fontSize=9
    )

    table_data = [[
        Paragraph("Job Role", header_style),
        Paragraph("Score", header_style),
        Paragraph("Matched Skills", header_style),
        Paragraph("Missing Skills", header_style)
    ]]

    for job in recommendations:

        matched = ", ".join(
            str(skill)
            for skill in job.get("matched_skills", [])
        ) or "-"

        missing = ", ".join(
            str(skill)
            for skill in job.get("missing_skills", [])
        ) or "-"

        table_data.append([
            Paragraph(
                escape(str(job.get("title", ""))),
                styles["Normal"]
            ),
            Paragraph(
                escape(str(job.get("score", 0))) + "%",
                styles["Normal"]
            ),
            Paragraph(escape(matched), styles["Normal"]),
            Paragraph(escape(missing), styles["Normal"])
        ])

    if recommendations:

        report_table = Table(
            table_data,
            colWidths=[105, 55, 175, 165],
            repeatRows=1
        )

        report_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#334155")),
            ("GRID", (0, 0), (-1, -1), 0.5,
             colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F1F5F9")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8)
        ]))

        story.append(report_table)

    else:

        story.append(
            Paragraph(
                "No job recommendations available.",
                styles["Normal"]
            )
        )

    story.append(Spacer(1, 25))

    story.append(
        Paragraph(
            "Generated by SmartHire AI - MCA Capstone Project",
            styles["Italic"]
        )
    )

    # Generate PDF
    document.build(story)

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resume_analysis_{analysis_id}.pdf"
    )
# Skills Analytics Dashboard Route

@app.route("/admin/analytics")
def admin_analytics():

    # Check login
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Check admin permission
    if session.get("user_role") != "admin":
        return redirect(url_for("dashboard"))

    # Fetch resume skills from database
    with sqlite3.connect(DATABASE) as conn:

        rows = conn.execute("""
            SELECT skills_json
            FROM resume_analyses
        """).fetchall()

    skill_counts = {}
    skill_names = {}

    # Count skills in uploaded resumes
    for row in rows:

        try:
            skills = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            continue

        # Avoid duplicate counting within one resume
        seen = set()

        for skill in skills:

            name = str(skill).strip()

            if not name:
                continue

            key = name.casefold()

            if key not in seen:

                skill_counts[key] = (
                    skill_counts.get(key, 0) + 1
                )

                skill_names[key] = name
                seen.add(key)

    # Sort skills by frequency
    sorted_skills = sorted(
        skill_counts.items(),
        key=lambda item: item[1],
        reverse=True
    )

    max_count = max(
        skill_counts.values(),
        default=0
    )

    analytics = []

    for key, count in sorted_skills:

        analytics.append({
            "skill": skill_names[key],
            "count": count,
            "bar_width": round(
                (count / max_count) * 100, 2
            ) if max_count else 0
        })

    return render_template(
        "admin_analytics.html",
        analytics=analytics,
        total_resumes=len(rows)
    )

if __name__ == "__main__":
    app.run(debug=True)

