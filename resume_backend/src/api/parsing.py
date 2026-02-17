import re
from typing import Any, Dict, List, Optional

from pypdf import PdfReader
from docx import Document


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(data: bytes) -> str:
    """Extract text from a PDF blob."""
    reader = PdfReader(io=data)  # type: ignore[arg-type]
    parts: List[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return _clean_text("\n".join(parts))


def extract_text_from_docx(data: bytes) -> str:
    """Extract text from a DOCX blob."""
    # python-docx expects a file-like object; it can accept a bytes buffer.
    import io

    doc = Document(io.BytesIO(data))
    parts: List[str] = []
    for p in doc.paragraphs:
        if p.text:
            parts.append(p.text)
    return _clean_text("\n".join(parts))


def extract_text(filename: str, content_type: Optional[str], data: bytes) -> str:
    """Extract text based on content_type/extension."""
    name = (filename or "").lower()
    ct = (content_type or "").lower()

    if name.endswith(".pdf") or ct == "application/pdf":
        # pypdf expects a file-like. Provide it via BytesIO, but PdfReader supports bytes in recent versions.
        import io

        reader = PdfReader(io.BytesIO(data))
        parts: List[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return _clean_text("\n".join(parts))

    if name.endswith(".docx") or "wordprocessingml" in ct or ct == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(data)

    # Fallback: treat as utf-8-ish text
    try:
        return _clean_text(data.decode("utf-8", errors="ignore"))
    except Exception:
        return ""


def _find_emails(text: str) -> List[str]:
    return list({m.group(0) for m in re.finditer(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)})


def _find_phone(text: str) -> Optional[str]:
    m = re.search(r"(\+?\d[\d \-\(\)]{8,}\d)", text)
    return m.group(1).strip() if m else None


def _guess_name(text: str) -> Optional[str]:
    # Very naive: take first non-empty line that looks like a name (2-4 capitalized words).
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > 80:
            continue
        if re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+){1,3}", line):
            return line
    return None


# PUBLIC_INTERFACE
def extract_structured_fields(raw_text: str) -> Dict[str, Any]:
    """
    Produce a lightweight structured representation from raw resume text.

    This is intentionally heuristic (no external AI dependency), but provides fields
    that can later be replaced with an AI-powered extractor.
    """
    skills = sorted(
        {
            s.strip().lower()
            for s in re.findall(r"\b(python|java|javascript|typescript|react|node|sql|postgres|aws|gcp|azure|docker|kubernetes|fastapi|django|flask)\b", raw_text, re.I)
        }
    )
    return {
        "name": _guess_name(raw_text),
        "emails": _find_emails(raw_text),
        "phone": _find_phone(raw_text),
        "skills": skills,
        "summary": raw_text[:800],
    }
