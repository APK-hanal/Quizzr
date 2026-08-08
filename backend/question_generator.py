import json
import os
import random
import re
from typing import Any

from openai import OpenAI

from backend.pdf_parser import extract_topics, split_into_chunks


def _normalize_difficulty(value: str) -> str:
    value = value.lower().strip()
    if value in {"easy", "medium", "hard"}:
        return value
    return "medium"


def _filter_by_difficulty(questions: list[dict], difficulty: str) -> list[dict]:
    if difficulty == "mixed":
        return questions
    return [q for q in questions if q.get("difficulty", "medium") == difficulty]


def _build_local_question(sentence: str, topic: str, index: int) -> dict:
    words = re.findall(r"\b[A-Za-z]{4,}\b", sentence)
    key_term = words[index % len(words)] if words else topic
    distractors = [
        "An unrelated concept from another field",
        "The opposite of what the text describes",
        "A common misconception about this topic",
    ]
    options = [
        sentence[:120] + ("..." if len(sentence) > 120 else ""),
        distractors[0],
        distractors[1],
        distractors[2],
    ]
    random.shuffle(options)
    correct_index = options.index(sentence[:120] + ("..." if len(sentence) > 120 else ""))

    return {
        "question": f"According to the material, which statement best describes {key_term}?",
        "options": options,
        "correct_index": correct_index,
        "explanation": f"This answer is supported by the PDF content about {topic}.",
        "topic": topic,
        "difficulty": random.choice(["easy", "medium", "hard"]),
    }


def generate_local_questions(
    text: str,
    topics: list[str],
    count: int = 10,
    difficulty: str = "mixed",
) -> list[dict]:
    chunks = split_into_chunks(text)
    if not chunks:
        return []

    questions: list[dict] = []
    for i in range(count):
        chunk = chunks[i % len(chunks)]
        topic = topics[i % len(topics)] if topics else "General"
        questions.append(_build_local_question(chunk, topic, i))

    return _filter_by_difficulty(questions, difficulty)[:count]


def generate_ai_questions(
    text: str,
    topics: list[str],
    count: int = 10,
    difficulty: str = "mixed",
) -> list[dict]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return generate_local_questions(text, topics, count, difficulty)

    client = OpenAI(api_key=api_key)
    excerpt = text[:12000]
    topic_list = ", ".join(topics) if topics else "General concepts from the document"

    prompt = f"""
You are an educational assistant. Read the PDF excerpt and create {count} multiple-choice quiz questions.

Topics to cover: {topic_list}
Difficulty mode: {difficulty}

Return ONLY valid JSON in this shape:
{{
  "questions": [
    {{
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "string",
      "topic": "string",
      "difficulty": "easy|medium|hard"
    }}
  ]
}}

Rules:
- Questions must be answerable from the excerpt.
- Each question needs exactly 4 options.
- Use varied topics from the PDF.
- Keep explanations short and educational.

PDF excerpt:
{excerpt}
"""

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "You generate educational quiz questions and return JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    payload = json.loads(response.choices[0].message.content or "{}")
    questions = payload.get("questions", [])
    cleaned: list[dict[str, Any]] = []

    for item in questions:
        options = item.get("options", [])
        if len(options) != 4:
            continue
        cleaned.append(
            {
                "question": str(item.get("question", "")).strip(),
                "options": [str(option).strip() for option in options],
                "correct_index": int(item.get("correct_index", 0)),
                "explanation": str(item.get("explanation", "")).strip(),
                "topic": str(item.get("topic", "General")).strip(),
                "difficulty": _normalize_difficulty(str(item.get("difficulty", "medium"))),
            }
        )

    if not cleaned:
        return generate_local_questions(text, topics, count, difficulty)

    return _filter_by_difficulty(cleaned, difficulty)[:count]


def analyze_pdf_content(text: str) -> dict[str, Any]:
    topics = extract_topics(text)
    word_count = len(re.findall(r"\b\w+\b", text))
    estimated_questions = max(5, min(20, word_count // 120 or 5))
    return {
        "topics": topics,
        "word_count": word_count,
        "estimated_questions": estimated_questions,
    }
