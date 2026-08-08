import re
from io import BytesIO

from pypdf import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.strip())
    return "\n\n".join(page for page in pages if page)


def extract_topics(text: str, max_topics: int = 8) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    topics: list[str] = []

    for line in lines:
        if len(line) > 120:
            continue
        if re.match(r"^(chapter|section|topic|unit|module)\s+\d", line, re.I):
            topics.append(line[:80])
        elif re.match(r"^\d+(\.\d+)*\s+[A-Z]", line):
            topics.append(line[:80])
        elif line.isupper() and 3 < len(line.split()) <= 8:
            topics.append(line.title()[:80])

    if not topics:
        words = re.findall(r"\b[A-Za-z]{5,}\b", text.lower())
        stopwords = {
            "about", "after", "again", "being", "between", "could",
            "during", "every", "first", "found", "other", "should",
            "their", "there", "these", "those", "through", "under",
            "where", "which", "while", "would", "within", "without",
        }
        freq: dict[str, int] = {}
        for word in words:
            if word in stopwords:
                continue
            freq[word] = freq.get(word, 0) + 1
        ranked = sorted(freq.items(), key=lambda item: item[1], reverse=True)
        topics = [word.title() for word, _ in ranked[:max_topics]]

    seen = set()
    unique_topics = []
    for topic in topics:
        key = topic.lower()
        if key not in seen:
            seen.add(key)
            unique_topics.append(topic)
    return unique_topics[:max_topics]


def split_into_chunks(text: str, chunk_size: int = 900) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= chunk_size:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks
