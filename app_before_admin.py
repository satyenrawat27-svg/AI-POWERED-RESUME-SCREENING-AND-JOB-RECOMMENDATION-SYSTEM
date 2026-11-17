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
app.secret_key = "smarthire_local_dev_secret_change_later"
# Database file location
DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database.db"
)


# Create database and table
# Create database and tables
def init_db():

    with sqlite3.connect(DATABASE) as conn:

        # Existing resume analysis table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_filename TEXT NOT NULL,
                skills_json TEXT NOT NULL,
                recommendations_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # New users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add user_id to existing history table
        columns = [
            row[1] for row in
            conn.execute(
                "PRAGMA table_info(resume_analyses)"
            ).fetchall()
        ]

        if "user_id" not in columns:
            conn.execute("""
                ALTER TABLE resume_analyses
                ADD COLUMN user_id INTEGER
            """)

        conn.commit()
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resume_filename TEXT NOT NULL,
                skills_json TEXT NOT NULL,
                recommendations_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
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

    for job in JOBS:

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
                SELECT id, name, email, password_hash
                FROM users
                WHERE email = ?
            """, (email,)).fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

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

if __name__ == "__main__":
    app.run(debug=True)

