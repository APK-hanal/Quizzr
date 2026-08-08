import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.pdf_parser import extract_text_from_pdf
from backend.question_generator import (
    analyze_pdf_content,
    generate_ai_questions_async,
    generate_summary_async,
    generate_teacher_quiz_pool,
    build_quiz_versions,
)



load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

MAX_FILE_SIZE = 10 * 1024 * 1024
EXCERPT_LIMIT = 12000

app = FastAPI(title="Quizzr", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "ai_enabled": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.post("/api/analyze")
async def analyze_pdf(
    file: UploadFile = File(...),
    question_count: int = Form(10),
    difficulty: str = Form("mixed"),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size must be under 10MB.")

    try:
        text = extract_text_from_pdf(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc

    if len(text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Not enough readable text found in this PDF. Try a text-based PDF.",
        )

    analysis = analyze_pdf_content(text)
    question_count = max(5, min(20, question_count))

    questions, used_ai = await generate_ai_questions_async(
        text=text,
        topics=analysis["topics"],
        count=question_count,
        difficulty=difficulty,
    )

    return {
        "document_name": file.filename,
        "topics": analysis["topics"],
        "word_count": analysis["word_count"],
        "estimated_questions": analysis["estimated_questions"],
        "question_count": len(questions),
        "ai_mode": "openai" if used_ai else "local",
        "truncated": len(text) > EXCERPT_LIMIT,
        "questions": questions,
    }


@app.post("/api/check-answer")
async def check_answer(
    selected_index: int = Form(...),
    correct_index: int = Form(...),
    explanation: str = Form(""),
    misconception: str = Form(""),
):
    """
    Frontend calls this per-question after the user picks an answer.
    Keeps the misconception-correction logic server-side and centralized,
    so the demo can show 'here's the misconception you fell for' live.
    """
    is_correct = selected_index == correct_index
    return {
        "is_correct": is_correct,
        "feedback": explanation if is_correct else misconception,
    }



@app.post("/api/summarize")
async def summarize_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size must be under 10MB.")

    try:
        text = extract_text_from_pdf(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc

    if len(text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Not enough readable text found in this PDF. Try a text-based PDF.",
        )

    analysis = analyze_pdf_content(text)
    summary, used_ai = await generate_summary_async(text, analysis["topics"])

    return {
        "document_name": file.filename,
        "topics": analysis["topics"],
        "word_count": analysis["word_count"],
        "ai_mode": "openai" if used_ai else "local",
        "truncated": len(text) > EXCERPT_LIMIT,
        "summary": summary,
    }

VALID_VERSION_LABELS = ["A", "B", "C", "D"]


@app.post("/api/teacher-quiz")
async def teacher_quiz(
    file: UploadFile = File(...),
    question_count: int = Form(10),
    num_versions: int = Form(1),
    easy_pct: int = Form(40),
    medium_pct: int = Form(40),
    hard_pct: int = Form(20),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size must be under 10MB.")

    try:
        text = extract_text_from_pdf(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc

    if len(text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Not enough readable text found in this PDF. Try a text-based PDF.",
        )

    total_pct = easy_pct + medium_pct + hard_pct
    if total_pct != 100:
        raise HTTPException(status_code=400, detail=f"Difficulty percentages must sum to 100, got {total_pct}.")

    question_count = max(5, min(30, question_count))
    num_versions = max(1, min(4, num_versions))

    analysis = analyze_pdf_content(text)
    ratios = {"easy": easy_pct / 100, "medium": medium_pct / 100, "hard": hard_pct / 100}

    pool, used_ai = await generate_teacher_quiz_pool(
        text=text,
        topics=analysis["topics"],
        total_count=question_count,
        ratios=ratios,
    )

    version_labels = VALID_VERSION_LABELS[:num_versions]
    versions = build_quiz_versions(pool, version_labels)

    return {
        "document_name": file.filename,
        "topics": analysis["topics"],
        "word_count": analysis["word_count"],
        "ai_mode": "openai" if used_ai else "local",
        "question_count": len(pool),
        "versions": versions,  # {"A": [...], "B": [...], ...}
    }

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")