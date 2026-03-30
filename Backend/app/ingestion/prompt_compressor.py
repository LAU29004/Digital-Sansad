"""
app/ingestion/prompt_compressor.py
===================================
Pure compression engine for the legislative bill ingestion pipeline.

Pipeline:
    PDF -> TEXT (pdfplumber + PyMuPDF fallback) -> L1 STRIP
        -> L2 DEDUP (all-MiniLM-L6-v2 embeddings)
        -> L3 EXTRACT (TF-IDF)
        -> L4 CLASSIFY -> JSON

Embeddings : sentence-transformers all-MiniLM-L6-v2  (local, no API key)
LLM        : Gemini gemini-2.0-flash                  (via GEMINI_API_KEY)

LAZY LOADING: All heavy libraries (sentence_transformers, sklearn, numpy,
tiktoken, pdfplumber, fitz) are imported INSIDE functions only.
FastAPI / gunicorn can import this module with zero heavy-lib loading.

Public API:
    from app.ingestion.prompt_compressor import compress_pdf_to_json
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# NOTE: NO heavy imports at module level.
# numpy, sklearn, tiktoken, sentence_transformers, pdfplumber, fitz
# are ALL imported lazily inside the functions that need them.
# ---------------------------------------------------------------------------

log = logging.getLogger("prompt_compressor")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL  = "all-MiniLM-L6-v2"
DEDUP_THRESHOLD  = 0.90
KEEP_RATIO       = 0.20
MIN_SENTENCE_LEN = 25
MIN_KEEP         = 8
MIN_PAGE_CHARS   = 30

# ---------------------------------------------------------------------------
# Title extraction patterns
# ---------------------------------------------------------------------------

_TITLE_CITATION_RE = re.compile(
    r"(the\s+[A-Z][A-Za-z\s,()'-]{5,80}(?:act|bill|code)[,\s]*(?:20\d{2}|19\d{2}))",
    re.IGNORECASE,
)
_TITLE_CAPS_RE = re.compile(
    r"^((?:[A-Z][A-Z\s,()'-]{4,100})(?:ACT|BILL|CODE)(?:[,\s]*(?:20\d{2}|19\d{2}))?)$"
)
_TITLE_BILLNO_RE = re.compile(
    r"(bill\s+no[\.\s]+\d+\s+of\s+(?:20\d{2}|19\d{2}))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Section keyword map
# ---------------------------------------------------------------------------

SECTION_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (
        ["penalty", "penalt", "fine", "punish", "imprison", "offence",
         "liable", "crore", "lakh", "rupee", "consequence", "forfeit",
         "conviction", "contravention"],
        "penalties",
    ),
    (
        ["right", "entitle", "citizen", "freedom", "benefit", "protect",
         "data principal", "individual", "person shall have", "grievance",
         "redress", "complaint"],
        "citizen_rights",
    ),
    (
        ["authority", "board", "tribunal", "commission", "committee",
         "regulator", "enforc", "directorate", "designated officer",
         "nodal", "superintend"],
        "regulatory_body",
    ),
    (
        ["shall", "must", "obligat", "duty", "comply", "requirement",
         "responsible", "required to", "bound to", "incumbent"],
        "obligations",
    ),
    (
        ["define", "meaning", "means", "term", "expression",
         "called", "interpret", "for the purpose", "herein"],
        "definitions",
    ),
    (
        ["amend", "repeal", "replace", "modify", "substitut",
         "omit", "insert", "notwithstanding", "overrid"],
        "amendments",
    ),
    (
        ["appeal", "appellate", "review", "revision", "challenge",
         "dispute", "object", "aggrieved", "redressal"],
        "appeal_mechanism",
    ),
    (
        ["schedule", "annexure", "appendix", "form", "part i",
         "part ii", "part iii", "first schedule", "second schedule"],
        "schedules",
    ),
    (
        ["offence", "cognizable", "bailable", "non-bailable",
         "warrant", "arrest", "prosecution", "court", "magistrate"],
        "enforcement",
    ),
]

# ---------------------------------------------------------------------------
# Boilerplate patterns
# ---------------------------------------------------------------------------

BOILERPLATE_PATTERNS: list[str] = [
    r"(?i)be it enacted by parliament.*?following.*?enacted",
    r"(?i)the\s+gazette\s+of\s+india.*?(?=\n\n|\Z)",
    r"(?i)ministry of (law and justice|finance|home affairs).*?\n",
    r"(?i)assented to by the president.*?\n",
    r"(?i)received the assent.*?\n",
    r"(?i)short title.*?commencement.*?\n{1,3}",
    r"\b\d{1,2}(?:st|nd|rd|th)\s+day\s+of\s+\w+,?\s+\d{4}\b",
    r"(?i)sd/-.*?\n",
    r"(?i)secretary to the government.*?\n",
    r"(?i)no\.\s*\d+[-/]\d+.*?\n",
    r"\[.*?see\s+section.*?\]",
    r"(?i)statement of objects and reasons.*?(?=\n\n|\Z)",
    r"(?i)financial memorandum.*?(?=\n\n|\Z)",
    r"(?i)memorandum regarding delegated legislation.*?(?=\n\n|\Z)",
    r"(?i)annexure.*?explanatory note.*?(?=\n\n|\Z)",
    r"(?m)^\s*\d+\s*$",
    r"(?m)^\s*[-_]{5,}\s*$",
]

LEGAL_SIGNAL_WORDS: list[str] = [
    "shall", "penalty", "offence", "right", "obligation", "liable",
    "prohibited", "authority", "citizen", "fine", "imprisonment",
    "board", "tribunal", "appeal", "amendment", "repeal", "section",
    "data", "privacy", "compliance", "regulation", "enforcement",
    "notwithstanding", "pursuant", "thereof", "herein", "aggrieved",
    "cognizable", "bailable", "warrant", "prosecution", "conviction",
]

# ---------------------------------------------------------------------------
# Lazy singletons — typed as Optional[object] to avoid importing heavy types
# ---------------------------------------------------------------------------

_tokenizer:   Optional[object] = None
_embed_model: Optional[object] = None


def _get_embed_model() -> object:
    """
    Lazily load the sentence-transformers embedding model.
    First call triggers the import and model download; subsequent calls
    return the cached singleton immediately.
    """
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer  # heavy import — lazy
        log.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def _get_tokenizer() -> object:
    """
    Lazily load the tiktoken tokenizer.
    """
    global _tokenizer
    if _tokenizer is None:
        import tiktoken  # heavy import — lazy
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


def _count_tokens(text: str) -> int:
    tokenizer = _get_tokenizer()
    return len(tokenizer.encode(text))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Data class  (pure Python — no heavy deps)
# ---------------------------------------------------------------------------

@dataclass
class CompressedBill:
    title:             str
    year:              str
    original_tokens:   int
    compressed_tokens: int
    compression_ratio: float
    sections:          dict[str, str]


# ---------------------------------------------------------------------------
# PDF extraction  (pdfplumber -> PyMuPDF fallback)
# Both libraries imported lazily inside each function.
# ---------------------------------------------------------------------------

def _extract_text_pymupdf(pdf_path: str) -> str:
    try:
        import fitz  # PyMuPDF — heavy import, lazy  # noqa: F401
    except ImportError:
        log.error("PyMuPDF not installed. Run: pip install pymupdf")
        return ""

    pages:      list[str] = []
    page_count: int       = 0
    try:
        doc        = fitz.open(pdf_path)
        page_count = doc.page_count
        log.info("  PyMuPDF: opened %d pages.", page_count)
        for i, page in enumerate(doc):
            try:
                text = page.get_text("text").strip()
                if len(text) >= MIN_PAGE_CHARS:
                    pages.append(text)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log.warning("  PyMuPDF page %d/%d failed: %s", i + 1, page_count, exc)
        doc.close()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        log.error("  PyMuPDF failed to open %s: %s", pdf_path, exc)
        return ""

    combined = "\n\n".join(pages)
    log.info("  PyMuPDF: extracted %d chars from %d/%d pages.",
             len(combined), len(pages), page_count)
    return combined


def _extract_text_from_pdf(pdf_path: str) -> str:
    try:
        import pdfplumber  # heavy import — lazy
    except ImportError:
        raise ImportError("pdfplumber is required: pip install pdfplumber")

    pages: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                try:
                    text = (page.extract_text() or "").strip()
                    if len(text) >= MIN_PAGE_CHARS:
                        pages.append(text)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    log.warning("Page %d/%d failed: %s", i + 1, total, exc)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        log.warning("pdfplumber failed: %s -- trying PyMuPDF.", exc)

    text = "\n\n".join(pages)
    if text.strip():
        log.info("  pdfplumber extracted %d chars.", len(text))
        return text

    log.warning("  pdfplumber found no text -- trying PyMuPDF fallback ...")
    pymupdf_text = _extract_text_pymupdf(pdf_path)
    if pymupdf_text.strip():
        return pymupdf_text

    log.error("  Both extractors failed for %s.", pdf_path)
    return ""


# ---------------------------------------------------------------------------
# Title / year extraction  (stdlib only — no heavy deps)
# ---------------------------------------------------------------------------

def _extract_title(raw_text: str) -> str:
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    head  = lines[:30]
    for line in head:
        m = _TITLE_CAPS_RE.match(line)
        if m:
            cleaned = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:-")
            if len(cleaned) > 8:
                return cleaned.upper()
    for line in head:
        m = _TITLE_CITATION_RE.search(line)
        if m:
            cleaned = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:-")
            if len(cleaned) > 8:
                return cleaned.title()
    m = _TITLE_CITATION_RE.search(raw_text)
    if m:
        cleaned = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:-")
        if len(cleaned) > 8:
            return cleaned.title()
    m = _TITLE_BILLNO_RE.search(raw_text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" .,;:-").upper()
    log.warning("Title extraction failed.")
    return "Unknown Bill"


def _extract_year(raw_text: str) -> str:
    for m in re.finditer(r"\b(20\d{2}|19\d{2})\b", raw_text):
        ctx = raw_text[max(0, m.start() - 30): m.end() + 30].lower()
        if any(kw in ctx for kw in ("act", "bill", "no.", "code")):
            return m.group(1)
    m = re.search(r"\b(20\d{2}|19\d{2})\b", raw_text)
    return m.group(1) if m else "Unknown"


# ---------------------------------------------------------------------------
# L1 strip  (stdlib only)
# ---------------------------------------------------------------------------

def _layer1_strip(text: str) -> str:
    for pattern in BOILERPLATE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"(\(\w+\)\s*){3,}", " ", text)
    text = re.sub(r"(\b\d+\.\s*){3,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# L2 dedup  (all-MiniLM-L6-v2 local embeddings — lazy)
# ---------------------------------------------------------------------------

def _layer2_dedup(text: str) -> str:
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) > 40
    ]
    if len(sentences) < 2:
        return text

    # Heavy imports — lazy
    from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401

    model      = _get_embed_model()
    embeddings = model.encode(sentences, batch_size=128, show_progress_bar=False)  # type: ignore[attr-defined]
    sim        = cosine_similarity(embeddings)

    kept:    list[str] = []
    dropped: set[int]  = set()
    for i, sent in enumerate(sentences):
        if i in dropped:
            continue
        kept.append(sent)
        for j in range(i + 1, len(sentences)):
            if j not in dropped and sim[i][j] >= DEDUP_THRESHOLD:
                dropped.add(j)

    log.debug("L2 dedup: %d -> %d sentences (%d dropped).",
              len(sentences), len(kept), len(dropped))
    return " ".join(kept)


# ---------------------------------------------------------------------------
# L3 extract  (TF-IDF — lazy)
# ---------------------------------------------------------------------------

def _layer3_extract(text: str, keep_ratio: float = KEEP_RATIO) -> str:
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) > MIN_SENTENCE_LEN
    ]
    if len(sentences) < MIN_KEEP:
        return text

    try:
        # Heavy imports — lazy
        import numpy as np  # noqa: F401
        from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401

        vectorizer   = TfidfVectorizer(stop_words="english", max_features=10000)
        tfidf_matrix = vectorizer.fit_transform(sentences)
        scores       = np.array(tfidf_matrix.sum(axis=1)).flatten().astype(float)
    except Exception:
        return text

    for i, sent in enumerate(sentences):
        lower = sent.lower()
        hits  = sum(1 for w in LEGAL_SIGNAL_WORDS if w in lower)
        scores[i] += hits * 0.4
        if re.search(r"\bsection\s+\d+", lower):
            scores[i] += 0.5

    n_keep      = max(MIN_KEEP, int(len(sentences) * keep_ratio))
    top_indices = sorted(np.argsort(scores)[-n_keep:])
    return " ".join(sentences[i] for i in top_indices)


# ---------------------------------------------------------------------------
# L4 classify  (stdlib only)
# ---------------------------------------------------------------------------

def _classify_sentence(sentence: str) -> str:
    lower  = sentence.lower()
    scores: dict[str, int] = {}
    for keywords, label in SECTION_KEYWORD_MAP:
        hits = sum(1 for kw in keywords if kw in lower)
        if hits:
            scores[label] = scores.get(label, 0) + hits
    return max(scores, key=scores.__getitem__) if scores else "general"


def _layer4_classify(
    compressed_text: str,
    raw_text:        str,
    orig_tokens:     int,
    comp_tokens:     int,
) -> CompressedBill:
    title     = _extract_title(raw_text)
    year      = _extract_year(raw_text)
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", compressed_text)
        if len(s.strip()) > MIN_SENTENCE_LEN
    ]
    grouped: dict[str, list[str]] = {}
    for sent in sentences:
        grouped.setdefault(_classify_sentence(sent), []).append(sent)
    sections: dict[str, str] = {k: " ".join(v) for k, v in grouped.items() if v}
    if not sections:
        log.warning("L4: no sections -- using general fallback.")
        sections = {"general": compressed_text.strip() or raw_text[:3000].strip()}
    return CompressedBill(
        title             = title,
        year              = year,
        original_tokens   = orig_tokens,
        compressed_tokens = comp_tokens,
        compression_ratio = round(orig_tokens / max(comp_tokens, 1), 1),
        sections          = sections,
    )


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def compress_pdf(pdf_path: str) -> CompressedBill:
    log.info("Compressing: %s", pdf_path)
    try:
        raw = _extract_text_from_pdf(pdf_path)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        log.error("PDF extraction failed: %s", exc)
        raw = ""

    if not raw.strip():
        log.error("Empty extraction -- returning fallback for: %s", pdf_path)
        return CompressedBill("Unknown Bill", "Unknown", 0, 0, 0.0, {"general": ""})

    orig_tokens = _count_tokens(raw)
    log.info("  Raw tokens      : %d", orig_tokens)

    t1     = _layer1_strip(raw)
    t1_tok = _count_tokens(t1)
    log.info("  After L1 strip  : %d tokens  (-%d%%)", t1_tok,
             100 - t1_tok * 100 // max(orig_tokens, 1))

    t2     = _layer2_dedup(t1)
    t2_tok = _count_tokens(t2)
    log.info("  After L2 dedup  : %d tokens  (-%d%%)", t2_tok,
             100 - t2_tok * 100 // max(orig_tokens, 1))

    t3          = _layer3_extract(t2)
    comp_tokens = _count_tokens(t3)
    log.info("  After L3 extract: %d tokens  (-%d%%)", comp_tokens,
             100 - comp_tokens * 100 // max(orig_tokens, 1))

    bill = _layer4_classify(t3, raw, orig_tokens, comp_tokens)
    log.info("  Final ratio     : %.1fx  |  title: %s  |  sections: %s",
             bill.compression_ratio, bill.title, list(bill.sections.keys()))
    return bill


def compress_pdf_to_json(pdf_path: str) -> dict:
    bill = compress_pdf(pdf_path)
    return {
        "title":             bill.title,
        "year":              bill.year,
        "original_tokens":   bill.original_tokens,
        "compressed_tokens": bill.compressed_tokens,
        "compression_ratio": bill.compression_ratio,
        "sections":          bill.sections,
    }