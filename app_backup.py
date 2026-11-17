import sqlite3
import json
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os

app = Flask(__name__)
# Database file location
DATABASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database.db"
)


# Create database and table
def init_db():
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
def save_analysis(filename, skills, recommendations):
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("""
            INSERT INTO resume_analyses
            (resume_filename, skills_json, recommendations_json)
            VALUES (?, ?, ?)
        """, (
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


@app.route("/history")
def history():

    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT * FROM resume_analyses
            ORDER BY id DESC
        """).fetchall()

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

