import asyncio
import json
import os
import random
import re
from typing import Any

from google import genai
from google.genai import types

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


def _filter_by_difficulty(
    questions: list[dict],
    difficulty: str,
) -> list[dict]:
    if difficulty == "mixed":
        return questions

    return [
        question
        for question in questions
        if question.get("difficulty", "medium") == difficulty
    ]


def _build_local_question(
    sentence: str,
    topic: str,
    index: int,
    rng: random.Random,
) -> dict:
    words = re.findall(r"\b[A-Za-z]{4,}\b", sentence)
    key_term = words[index % len(words)] if words else topic

    correct = sentence[:120] + ("..." if len(sentence) > 120 else "")

    distractors = rng.sample(_LOCAL_DISTRACTOR_POOL, k=3)
    options = [correct] + distractors
    rng.shuffle(options)

    correct_index = options.index(correct)

    return {
        "question": (
            f"According to the material, which statement best describes "
            f"{key_term}?"
        ),
        "options": options,
        "correct_index": correct_index,
        "explanation": (
            f"This is supported directly by the text about {topic}."
        ),
        "misconception": (
            f"A common mistake is assuming {key_term} works the way it is "
            f"typically described in general knowledge, rather than how this "
            f"specific source defines it."
        ),
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
        _build_local_question(
            sentence=chunks[i % len(chunks)],
            topic=topics[i % len(topics)] if topics else "General",
            index=i,
            rng=rng,
        )
        for i in range(count)
    ]

    return _filter_by_difficulty(questions, difficulty)[:count]


def _clean_ai_questions(
    payload: dict,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []

    raw_questions = payload.get("questions", [])

    if not isinstance(raw_questions, list):
        return cleaned

    for item in raw_questions:
        if not isinstance(item, dict):
            continue

        options = item.get("options", [])

        if not isinstance(options, list) or len(options) != 4:
            continue

        try:
            correct_index = int(item.get("correct_index", -1))
        except (TypeError, ValueError):
            continue

        if not 0 <= correct_index < 4:
            continue

        question = str(item.get("question", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        misconception = (
            str(item.get("misconception", "")).strip()
            or "No common misconception was identified for this question."
        )
        topic = str(item.get("topic", "General")).strip()
        difficulty = _normalize_difficulty(
            str(item.get("difficulty", "medium"))
        )

        if not question or not explanation:
            continue

        cleaned.append(
            {
                "question": question,
                "options": [str(option).strip() for option in options],
                "correct_index": correct_index,
                "explanation": explanation,
                "misconception": misconception,
                "topic": topic or "General",
                "difficulty": difficulty,
            }
        )

    return cleaned


def _build_prompt(
    excerpt: str,
    topic_list: str,
    count: int,
    difficulty: str,
) -> str:
    return f"""
You are an educational assistant that specializes in correcting misconceptions.

Read the PDF excerpt and create {count} multiple-choice quiz questions.

Topics to cover:
{topic_list}

Difficulty mode:
{difficulty}

For each question, identify a realistic misconception that could lead a
student to choose a specific wrong answer. Briefly explain why that belief
is wrong. This is the most important part of the output.

Return only valid JSON. Do not use Markdown fences, a preamble, or extra text.

Use exactly this JSON shape:

{{
  "questions": [
    {{
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "Why the correct answer is right",
      "misconception": "A specific wrong belief and why it is wrong",
      "topic": "string",
      "difficulty": "easy|medium|hard"
    }}
  ]
}}

Rules:

- Questions must be answerable from the excerpt only.
- Each question must have exactly four options.
- Options must be plausible and distinct.
- correct_index must be an integer from 0 through 3.
- Distractors should reflect realistic misconceptions, not random nonsense.
- Keep explanation under two sentences.
- Keep misconception under two sentences.
- Do not use information that is not present in the excerpt.
- Return only the JSON object.

PDF excerpt:
{excerpt}
"""


def _extract_json(raw: str) -> dict:
    """
    Extract a JSON object from the model response.

    The model is instructed to return plain JSON, but this also handles
    occasional Markdown code fences.
    """
    raw = raw.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw.strip())


def _get_gemini_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


async def generate_ai_questions_async(
    text: str,
    topics: list[str],
    count: int = 10,
    difficulty: str = "mixed",
) -> tuple[list[dict], bool]:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return (
            generate_local_questions(
                text=text,
                topics=topics,
                count=count,
                difficulty=difficulty,
            ),
            False,
        )

    excerpt = text[:12000]

    topic_list = (
        ", ".join(topics)
        if topics
        else "General concepts from the document"
    )

    prompt = _build_prompt(
        excerpt=excerpt,
        topic_list=topic_list,
        count=count,
        difficulty=difficulty,
    )

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )

    try:
        client = _get_gemini_client(api_key)

        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            ),
            timeout=25,
        )

        response_text = response.text

        if not response_text:
            raise ValueError("Gemini returned an empty response")

        payload = _extract_json(response_text)
        cleaned = _clean_ai_questions(payload)

    except Exception as exc:
        print(
            f"[AI generation failed, falling back to local]: {exc}"
        )

        return (
            generate_local_questions(
                text=text,
                topics=topics,
                count=count,
                difficulty=difficulty,
            ),
            False,
        )

    result = _filter_by_difficulty(cleaned, difficulty)[:count]

    if not result:
        return (
            generate_local_questions(
                text=text,
                topics=topics,
                count=count,
                difficulty=difficulty,
            ),
            False,
        )

    return result, True


def analyze_pdf_content(text: str) -> dict[str, Any]:
    topics = extract_topics(text)
    word_count = len(re.findall(r"\b\w+\b", text))
    estimated_questions = max(
        5,
        min(20, word_count // 120 or 5),
    )

    return {
        "topics": topics,
        "word_count": word_count,
        "estimated_questions": estimated_questions,
    }