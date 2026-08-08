import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.pdf_parser import extract_text_from_pdf
from backend.question_generator import analyze_pdf_content, generate_ai_questions_async

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


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")