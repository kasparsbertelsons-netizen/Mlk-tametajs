"""PDF teksta un rāmja norāžu izvilkšana bez izdomātiem daudzumiem."""
import re

FRAME_PATTERNS = [
    ("GL rāmis", r"\bGL\s*Frame\b[^\n]{0,90}"),
    ("Koka karkass", r"\bTimber\s+frame\b[^\n]{0,90}"),
    ("CLT panelis", r"\bCLT\s*[-–]\s*\d+\s*mm\b"),
]
DIMENSION_RE = re.compile(r"\b(?:\d{2,5}\s*[x×]\s*\d{2,5}|\d{2,5}\s*mm)\b", re.I)


def extract_frame_mentions(page_texts: list[str]) -> list[dict]:
    """Atgriež tiešus citātus ar lapu numuriem; neveido konstrukciju tāmi."""
    found = []
    for page_number, text in enumerate(page_texts, start=1):
        for label, pattern in FRAME_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.I):
                found.append({
                    "page": page_number,
                    "category": label,
                    "evidence": " ".join(match.group(0).split()),
                    "status": "Nolasīts no PDF teksta; jāpārbauda rasējumā",
                })
    return found


def read_pdf(file_bytes: bytes) -> dict:
    if not file_bytes.startswith(b"%PDF"):
        raise ValueError("Fails nav atpazīts kā PDF.")
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("Nav instalēts PyMuPDF.") from error
    pages = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("Ar paroli aizsargāts PDF pagaidām netiek atbalstīts.")
        if len(doc) > 100:
            raise ValueError("PDF pārsniedz 100 lapu limitu.")
        for index, page in enumerate(doc):
            text = page.get_text("text", sort=True)
            pages.append({"page": index + 1, "text": text, "text_chars": len(text)})
    return {
        "pages": pages,
        "mentions": extract_frame_mentions([p["text"] for p in pages]),
        "requires_review": True,
    }
