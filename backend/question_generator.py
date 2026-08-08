import asyncio
import json
import os
import random
import re
from typing import Any

import google.generativeai as genai

from backend.pdf_parser import extract_topics, split_into_chunks

_LOCAL_DISTRACTOR_POOL = [
    "This is true only in a specific edge case, not generally",
    "This confuses correlation with causation from the text",
    "This applies to a different but related concept",
    "This was true historically but is outdated per the text",
    "This is a common oversimplification of the actual mechanism",
    "This reverses the actual relationship described in the text",
]


def _normalize_difficulty(value: str) -> str:
    value = (value or "").lower().strip()
    return value if value in {"easy", "medium", "hard"} else "medium"


def _filter_by_difficulty(questions: list[dict], difficulty: str) -> list[dict]:
    if difficulty == "mixed":
        return questions
    return [q for q in questions if q.get("difficulty", "medium") == difficulty]


def _build_local_question(sentence: str, topic: str, index: int, rng: random.Random) -> dict:
    words = re.findall(r"\b[A-Za-z]{4,}\b", sentence)
    key_term = words[index % len(words)] if words else topic
    correct = sentence[:120] + ("..." if len(sentence) > 120 else "")

    distractors = rng.sample(_LOCAL_DISTRACTOR_POOL, k=3)
    options = [correct] + distractors
    rng.shuffle(options)
    correct_index = options.index(correct)

    return {
        "question": f"According to the material, which statement best describes {key_term}?",
        "options": options,
        "correct_index": correct_index,
        "explanation": f"This is supported directly by the text about {topic}.",
        "misconception": f"A common mistake is assuming {key_term} works the way it's "
        f"typically described in general knowledge, rather than how this specific "
        f"source defines it.",
        "topic": topic,
        "difficulty": rng.choice(["easy", "medium", "hard"]),
    }


def generate_local_questions(
    text: str,
    topics: list[str],
    count: int = 10,
    difficulty: str = "mixed",
    seed: int | None = None,
) -> list[dict]:
    chunks = split_into_chunks(text)
    if not chunks:
        return []

    rng = random.Random(seed)
    questions = [
        _build_local_question(chunks[i % len(chunks)], topics[i % len(topics)] if topics else "General", i, rng)
        for i in range(count)
    ]
    return _filter_by_difficulty(questions, difficulty)[:count]


def _clean_ai_questions(payload: dict) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in payload.get("questions", []):
        options = item.get("options", [])
        if not isinstance(options, list) or len(options) != 4:
            continue
        try:
            correct_index = int(item.get("correct_index", -1))
        except (TypeError, ValueError):
            continue
        if not (0 <= correct_index < 4):
            continue

        cleaned.append(
            {
                "question": str(item.get("question", "")).strip(),
                "options": [str(o).strip() for o in options],
                "correct_index": correct_index,
                "explanation": str(item.get("explanation", "")).strip(),
                "misconception": str(item.get("misconception", "")).strip()
                or "No common misconception was identified for this question.",
                "topic": str(item.get("topic", "General")).strip(),
                "difficulty": _normalize_difficulty(str(item.get("difficulty", "medium"))),
            }
        )
    return cleaned


def _build_prompt(excerpt: str, topic_list: str, count: int, difficulty: str) -> str:
    return f"""
You are an educational assistant that specializes in correcting misconceptions.
Read the PDF excerpt and create {count} multiple-choice quiz questions.

Topics to cover: {topic_list}
Difficulty mode: {difficulty}

For EACH question, also identify a realistic misconception a student might hold
that would lead them to pick a specific wrong answer, and briefly explain why
it's wrong. This is the most important part of the output.

Return ONLY valid JSON, no markdown fences, no preamble, in this exact shape:
{{
  "questions": [
    {{
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "string - why the correct answer is right",
      "misconception": "string - a specific wrong belief a student might have, and why it's wrong",
      "topic": "string",
      "difficulty": "easy|medium|hard"
    }}
  ]
}}

Rules:
- Questions must be answerable from the excerpt only.
- Each question needs exactly 4 options, plausible and distinct.
- correct_index must be a valid index (0-3) into options.
- Distractor options should reflect real misconceptions, not random noise.
- Keep explanation and misconception each under 2 sentences.
- Return ONLY the JSON object, nothing else — no markdown code fences.

PDF excerpt:
{excerpt}
"""


_gemini_configured = False


def _ensure_gemini_configured(api_key: str) -> None:
    global _gemini_configured
    if not _gemini_configured:
        genai.configure(api_key=api_key)
        _gemini_configured = True


def _extract_json(raw: str) -> dict:
    """Gemini sometimes wraps JSON in ```json fences despite instructions. Strip them."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


async def generate_ai_questions_async(
    text: str,
    topics: list[str],
    count: int = 10,
    difficulty: str = "mixed",
) -> tuple[list[dict], bool]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return generate_local_questions(text, topics, count, difficulty), False

    excerpt = text[:12000]
    topic_list = ", ".join(topics) if topics else "General concepts from the document"
    prompt = _build_prompt(excerpt, topic_list, count, difficulty)

    cleaned: list[dict[str, Any]] = []
    try:
        _ensure_gemini_configured(api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

        response = await asyncio.wait_for(
            asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"},
            ),
            timeout=25,
        )
        payload = _extract_json(response.text)
        cleaned = _clean_ai_questions(payload)
    except Exception as exc:
        print(f"[AI generation failed, falling back to local]: {exc}")
        cleaned = []

    if not cleaned:
        return generate_local_questions(text, topics, count, difficulty), False

    result = _filter_by_difficulty(cleaned, difficulty)[:count]
    if not result:
        return generate_local_questions(text, topics, count, difficulty), False
    return result, True


def analyze_pdf_content(text: str) -> dict[str, Any]:
    topics = extract_topics(text)
    word_count = len(re.findall(r"\b\w+\b", text))
    estimated_questions = max(5, min(20, word_count // 120 or 5))
    return {
        "topics": topics,
        "word_count": word_count,
        "estimated_questions": estimated_questions,
    }