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

    request_count = count if difficulty == "mixed" else min(count * 2, 30)

    prompt = _build_prompt(
        excerpt=excerpt,
        topic_list=topic_list,
        count=request_count,
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

    filtered = _filter_by_difficulty(cleaned, difficulty)[:count]

    if not filtered:
        return (
            generate_local_questions(
                text=text,
                topics=topics,
                count=count,
                difficulty=difficulty,
            ),
            False,
        )

    if len(filtered) < count:
        shortfall = count - len(filtered)
        padding = generate_local_questions(
            text=text,
            topics=topics,
            count=shortfall,
            difficulty="mixed",
        )
        for q in padding:
            if difficulty != "mixed":
                q["difficulty"] = difficulty
        filtered.extend(padding)

    return filtered[:count], True

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

def _build_summary_prompt(excerpt: str, topic_list: str) -> str:
    return f"""
You are an educational assistant. Read the PDF excerpt and produce a clear,
well-structured summary for a student studying this material.

Topics identified: {topic_list}

Return ONLY valid JSON, no markdown fences, no preamble, in this exact shape:
{{
  "overview": "string - 2-3 sentence high-level summary of the whole document",
  "key_points": ["string", "string", ...],
  "definitions": [
    {{"term": "string", "definition": "string"}}
  ]
}}

Rules:
- overview: 2-3 sentences, plain language, no jargon unless defined.
- key_points: 5-8 bullet points, each one specific fact/concept from the excerpt, one sentence each.
- definitions: up to 6 important terms from the excerpt with a one-sentence definition each. Omit if the excerpt has no clear technical terms.
- Base everything strictly on the excerpt content, do not invent facts.
- Return ONLY the JSON object, nothing else.

PDF excerpt:
{excerpt}
"""


def _clean_summary(payload: dict) -> dict[str, Any]:
    overview = str(payload.get("overview", "")).strip()
    key_points = [
        str(p).strip() for p in payload.get("key_points", [])
        if str(p).strip()
    ][:8]
    definitions = [
        {"term": str(d.get("term", "")).strip(), "definition": str(d.get("definition", "")).strip()}
        for d in payload.get("definitions", [])
        if str(d.get("term", "")).strip() and str(d.get("definition", "")).strip()
    ][:6]
    return {"overview": overview, "key_points": key_points, "definitions": definitions}


def generate_local_summary(text: str, topics: list[str]) -> dict[str, Any]:
    """Fallback when no AI key is set or the AI call fails."""
    chunks = split_into_chunks(text)
    overview = chunks[0][:280] + ("..." if chunks and len(chunks[0]) > 280 else "") if chunks else "No readable content found."
    key_points = [c[:150] + ("..." if len(c) > 150 else "") for c in chunks[1:7]]
    return {
        "overview": overview,
        "key_points": key_points,
        "definitions": [{"term": t, "definition": "Mentioned as a key topic in this document."} for t in topics[:6]],
    }


async def generate_summary_async(text: str, topics: list[str]) -> tuple[dict[str, Any], bool]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return generate_local_summary(text, topics), False

    excerpt = text[:12000]
    topic_list = ", ".join(topics) if topics else "General concepts from the document"
    prompt = _build_summary_prompt(excerpt, topic_list)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

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
        cleaned = _clean_summary(payload)

    except Exception as exc:
        print(f"[Summary generation failed, falling back to local]: {exc}")
        return generate_local_summary(text, topics), False

    if not cleaned["overview"] and not cleaned["key_points"]:
        return generate_local_summary(text, topics), False

    return cleaned, True

def _difficulty_split(total: int, ratios: dict[str, float]) -> dict[str, int]:
    """Split total into per-difficulty counts based on ratios, no question lost to rounding."""
    raw = {k: total * v for k, v in ratios.items()}
    counts = {k: int(v) for k, v in raw.items()}
    remainder = total - sum(counts.values())
    # Give leftover questions to whichever buckets rounded down the most.
    remainders = sorted(ratios.keys(), key=lambda k: raw[k] - counts[k], reverse=True)
    for i in range(remainder):
        counts[remainders[i % len(remainders)]] += 1
    return counts


async def generate_teacher_quiz_pool(
    text: str,
    topics: list[str],
    total_count: int = 10,
    ratios: dict[str, float] | None = None,
) -> tuple[list[dict], bool]:
    """
    Generates a master pool of questions matching a difficulty distribution
    (default 40% easy / 40% medium / 20% hard). Calls the existing generator
    once per difficulty bucket so each bucket is reliably filled, instead of
    generating mixed and hoping the ratio lands right.
    """
    ratios = ratios or {"easy": 0.4, "medium": 0.4, "hard": 0.2}
    counts = _difficulty_split(total_count, ratios)

    pool: list[dict] = []
    any_ai = False
    for diff, n in counts.items():
        if n <= 0:
            continue
        questions, used_ai = await generate_ai_questions_async(text, topics, count=n, difficulty=diff)
        pool.extend(questions)
        any_ai = any_ai or used_ai

    return pool, any_ai


def _shuffle_question_options(question: dict, rng: random.Random) -> dict:
    """Returns a copy of the question with options shuffled and correct_index remapped."""
    options = list(question["options"])
    correct_option = options[question["correct_index"]]
    indices = list(range(len(options)))
    rng.shuffle(indices)
    new_options = [options[i] for i in indices]
    new_correct_index = new_options.index(correct_option)

    new_q = dict(question)
    new_q["options"] = new_options
    new_q["correct_index"] = new_correct_index
    return new_q


def build_quiz_versions(pool: list[dict], version_labels: list[str], seed_base: int = 42) -> dict[str, list[dict]]:
    """
    Builds N versions (e.g. A/B/C) from the same question pool: each version
    gets the questions in a different order, and each question's options
    shuffled independently, so no two versions look identical to students
    sitting next to each other.
    """
    versions: dict[str, list[dict]] = {}
    for i, label in enumerate(version_labels):
        rng = random.Random(seed_base + i)
        shuffled_order = pool[:]
        rng.shuffle(shuffled_order)
        versions[label] = [_shuffle_question_options(q, rng) for q in shuffled_order]
    return versions