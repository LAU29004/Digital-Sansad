"""
app/routers/chat.py
===================
AI chat endpoints consumed by ChatScreen and BillDetailsScreen onAskAI.

POST /chat           — full query pipeline:
                       1. Cheap HF LLM fills JSON schema from question
                       2. Match bills in PostgreSQL
                       3. Retrieve sections from ChromaDB
                       4. Chain-of-Density densification (cheap HF LLM)
                       5. Strong HF LLM generates final answer
POST /upload-pdf     — user uploads a PDF not in DB, compress + Gemini answer
POST /trigger-ingest — check if bill is in DB; if not, inform user scheduler
                       will pick it up automatically every 6 hours

LLM (answers)    : HuggingFace Inference API  meta-llama/Llama-3.3-70B-Instruct
LLM (schema/CoD) : HuggingFace Inference API  meta-llama/Llama-3.1-8B-Instruct
Embeddings       : sentence-transformers all-MiniLM-L6-v2  (local)
Upload-PDF LLM   : Gemini gemini-2.0-flash  (via GEMINI_API_KEY)
"""

import os
import re
import json
import time
import tempfile
import logging
from typing import Optional

import chromadb
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from huggingface_hub import InferenceClient
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.database import SessionLocal, engine as db_engine
from app.ingestion.prompt_compressor import compress_pdf_to_json
from app.models.bill import Bill

load_dotenv()
log    = logging.getLogger("chat_router")
router = APIRouter()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHROMA_DIR        = os.getenv("CHROMA_DIR",        "chroma_db")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION",  "bill_sections")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL",       "gemini-2.0-flash")
HF_TOKEN          = os.getenv("HF_TOKEN")

CHEAP_MODEL  = "meta-llama/Llama-3.1-8B-Instruct"
STRONG_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

MAX_SECTIONS_PER_BILL = 3
COD_ROUNDS            = 3
EMBED_MODEL           = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_chroma_col    = None
_embed_model   = None
_cheap_client  = None
_strong_client = None
_gemini_client = None


def _get_chroma():
    global _chroma_col
    if _chroma_col is None:
        client      = chromadb.PersistentClient(path=CHROMA_DIR)
        _chroma_col = client.get_or_create_collection(name=CHROMA_COLLECTION)
    return _chroma_col


def _get_embed():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def _get_cheap_client():
    global _cheap_client
    if _cheap_client is None:
        _cheap_client = InferenceClient(model=CHEAP_MODEL, token=HF_TOKEN, provider="auto")
    return _cheap_client


def _get_strong_client():
    global _strong_client
    if _strong_client is None:
        _strong_client = InferenceClient(model=STRONG_MODEL, token=HF_TOKEN, provider="novita")
    return _strong_client


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# HF chat helper
# ---------------------------------------------------------------------------

def _hf_chat(client: InferenceClient, system: str, user: str, max_tokens: int = 512) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    resp = client.chat_completion(messages=messages, max_tokens=max_tokens)
    text = resp.choices[0].message.content or ""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


# ---------------------------------------------------------------------------
# Step 1 — Cheap LLM fills JSON schema
# ---------------------------------------------------------------------------

BILL_SCHEMA = {
    "bill_number": "",
    "title":       "",
    "year":        "",
    "status":      "",
    "ministry":    "",
    "topic":       "",
}

SCHEMA_SYSTEM = """
You are a structured data extractor.
Given a user's question about Indian parliamentary bills, fill in the JSON schema below.
Rules:
- Only fill a field if the user clearly mentioned it.
- Leave fields as "" if not mentioned. Never guess or invent values.
- "title" should be 1-3 keywords from the bill subject, not a full sentence.
- "year" must be a 4-digit number or "".
- Return ONLY valid JSON. No explanation, no markdown fences.
""".strip()


def _fill_schema(question: str) -> dict:
    user_content = (
        f"User question: {question}\n\n"
        f"Fill this schema:\n{json.dumps(BILL_SCHEMA, indent=2)}"
    )
    raw = _hf_chat(_get_cheap_client(), SCHEMA_SYSTEM, user_content, max_tokens=300)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Schema LLM returned invalid JSON — using empty schema")
        return dict(BILL_SCHEMA)


# ---------------------------------------------------------------------------
# Step 2 — Match bills in PostgreSQL
# ---------------------------------------------------------------------------

def _match_bills(schema: dict, bill_number: Optional[str] = None, limit: int = 3) -> list[dict]:
    """
    If bill_number is explicitly passed (from the request), use it directly.
    Otherwise use the schema extracted by the cheap LLM.
    """
    clauses = ["compressed = true"]
    params  = {}

    # Explicit bill_number from request takes priority
    target = bill_number or schema.get("bill_number")
    if target:
        clauses.append("bill_number = :bill_number")
        params["bill_number"] = target
    else:
        if schema.get("title"):
            clauses.append("title ILIKE :title")
            params["title"] = f"%{schema['title']}%"
        if schema.get("year"):
            clauses.append("year = :year")
            params["year"] = schema["year"]
        if schema.get("status"):
            clauses.append("status ILIKE :status")
            params["status"] = f"%{schema['status']}%"

    where      = " AND ".join(clauses)
    params["limit"] = limit

    sql = text(f"""
        SELECT bill_number, title, year, status,
               original_tokens, compressed_tokens, compression_ratio
        FROM bills
        WHERE {where}
        ORDER BY last_seen_at DESC
        LIMIT :limit
    """)

    with db_engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "bill_id":           row[0],
            "title":             row[1],
            "year":              row[2],
            "status":            row[3],
            "original_tokens":   row[4],
            "compressed_tokens": row[5],
            "compression_ratio": row[6],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Step 3 — Retrieve sections from ChromaDB
# ---------------------------------------------------------------------------

def _retrieve_sections(question: str, bills: list[dict]) -> dict[str, list[str]]:
    col   = _get_chroma()
    model = _get_embed()
    q_emb = model.encode([question]).tolist()

    bill_sections: dict[str, list[str]] = {}

    for bill in bills:
        bid = bill["bill_id"]
        try:
            results = col.query(
                query_embeddings = q_emb,
                n_results        = MAX_SECTIONS_PER_BILL,
                where            = {"bill_number": bid},
                include          = ["documents", "metadatas"],
            )
            docs  = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]

            labeled = []
            for doc, meta in zip(docs, metas):
                sec_name = meta.get("section", f"chunk_{meta.get('chunk_index', 0)}")
                labeled.append(f"[{sec_name.upper()}]\n{doc}")

            bill_sections[bid] = labeled

        except Exception as exc:
            log.warning("Chroma query failed for bill %s: %s", bid, exc)
            bill_sections[bid] = []

    return bill_sections


# ---------------------------------------------------------------------------
# Step 4 — Chain-of-Density densification
# ---------------------------------------------------------------------------

COD_SYSTEM = """
You are a token-density optimizer for legal documents.
You will receive a passage from an Indian parliamentary bill.
Your job: rewrite it so that:
  - The output is the SAME length (±10%) as the input.
  - Every sentence contains MORE named entities: amounts, dates, section numbers,
    ministry names, article references, legal obligations, penalties.
  - No filler words, no repetition, no "as mentioned above".
  - Plain English. A citizen must still understand it.
Return ONLY the rewritten passage. No explanation.
""".strip()


def _chain_of_density(text: str, rounds: int = COD_ROUNDS) -> str:
    current = text
    for _ in range(rounds):
        current = _hf_chat(
            _get_cheap_client(),
            COD_SYSTEM,
            current,
            max_tokens=max(200, int(len(text.split()) * 1.5)),
        )
    return current


def _densify_sections(bill_sections: dict[str, list[str]], bills: list[dict]) -> str:
    bill_map      = {b["bill_id"]: b for b in bills}
    context_parts = []

    for bid, sections in bill_sections.items():
        if not sections:
            continue
        bill_info = bill_map.get(bid, {})
        context_parts.append(
            f"=== Bill {bid}: {bill_info.get('title', '')} ({bill_info.get('year', '')}) ==="
        )
        for sec_text in sections:
            densified = _chain_of_density(sec_text)
            context_parts.append(densified)

    return "\n\n".join(context_parts)


# ---------------------------------------------------------------------------
# Step 5 — Strong LLM answers
# ---------------------------------------------------------------------------

ANSWER_SYSTEM = """
You are a legal simplification assistant for Indian citizens.
Answer the user's question using ONLY the bill content provided.
Rules:
- Be direct. Lead with the answer, not with "according to the bill".
- Use plain English. No legal jargon.
- Cite section names (e.g. [PENALTIES], [CITIZEN_RIGHTS]) when relevant.
- If the bill content does not answer the question, say so clearly.
- Keep your answer under 200 words.
""".strip()


def _answer_with_strong_llm(question: str, context: str) -> str:
    user_content = f"Question: {question}\n\nBill content:\n{context}"
    return _hf_chat(_get_strong_client(), ANSWER_SYSTEM, user_content, max_tokens=400)


# ---------------------------------------------------------------------------
# Full pipeline (used by /chat)
# ---------------------------------------------------------------------------

def run_query_pipeline(
    question:    str,
    bill_number: Optional[str] = None,
) -> dict:
    """
    Runs the full 5-step pipeline and returns a dict with answer + sources.
    Raises HTTPException on failure so FastAPI handles it cleanly.
    """

    # Step 1 — schema
    schema = _fill_schema(question)
    log.info("Schema filled: %s", schema)

    # Step 2 — match bills
    bills = _match_bills(schema, bill_number=bill_number)
    if not bills:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No matching bills found in the database. "
                f"{'Bill ' + bill_number + ' may not be ingested yet. ' if bill_number else ''}"
                f"The scheduler checks for new bills every 6 hours."
            ),
        )

    # Step 3 — retrieve sections
    bill_sections = _retrieve_sections(question, bills)
    if not any(bill_sections.values()):
        raise HTTPException(
            status_code=404,
            detail="Bills found in PostgreSQL but no sections in ChromaDB. "
                   "Try /trigger-ingest to re-embed.",
        )

    # Step 4 — chain-of-density
    log.info("Running Chain-of-Density (%d rounds) ...", COD_ROUNDS)
    dense_context = _densify_sections(bill_sections, bills)

    # Step 5 — strong LLM answer
    log.info("Calling strong LLM for answer ...")
    answer = _answer_with_strong_llm(question, dense_context)

    # Build sources list for response
    sources = []
    for bill in bills:
        for sec in bill_sections.get(bill["bill_id"], []):
            label = sec.split("\n")[0]   # e.g. "[PENALTIES]"
            sources.append({
                "bill_number": bill["bill_id"],
                "title":       bill["title"],
                "section":     label,
            })

    return {
        "answer":      answer,
        "sources":     sources,
        "bills_used":  [{"bill_number": b["bill_id"], "title": b["title"]} for b in bills],
    }


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question:    str
    bill_number: Optional[str] = None


class ChatResponse(BaseModel):
    answer:      str
    sources:     list[dict]
    bill_number: Optional[str] = None
    bill_title:  Optional[str] = None
    bills_used:  list[dict]    = []


class UploadPdfResponse(BaseModel):
    answer:            str
    bill_title:        str
    year:              str
    compression_ratio: float
    sections_found:    list[str]


class IngestRequest(BaseModel):
    bill_number: str


class IngestResponse(BaseModel):
    status:      str
    bill_number: str
    message:     str


# ---------------------------------------------------------------------------
# POST /chat  — full query pipeline
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    db:   Session = Depends(get_db),
):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # If bill_number provided, verify it exists in DB first
    bill_title = None
    if body.bill_number:
        bill = db.query(Bill).filter(Bill.bill_number == body.bill_number).first()
        if not bill:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Bill {body.bill_number} is not in the database yet. "
                    f"The background scheduler checks for new bills every 6 hours. "
                    f"Please try again later."
                ),
            )
        bill_title = bill.title

    result = run_query_pipeline(
        question    = body.question,
        bill_number = body.bill_number,
    )

    return ChatResponse(
        answer      = result["answer"],
        sources     = result["sources"],
        bill_number = body.bill_number,
        bill_title  = bill_title,
        bills_used  = result["bills_used"],
    )


# ---------------------------------------------------------------------------
# POST /upload-pdf  — compress + Gemini answer (no DB storage)
# ---------------------------------------------------------------------------

@router.post("/upload-pdf", response_model=UploadPdfResponse)
async def upload_pdf(
    file:     UploadFile    = File(...),
    question: Optional[str] = Form("Summarise this bill in simple terms for a citizen."),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content  = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result   = compress_pdf_to_json(tmp_path)
        sections = result.get("sections", {})
        title    = result.get("title", file.filename)
        year     = result.get("year", "Unknown")
        ratio    = result.get("compression_ratio", 0.0)

        if not sections:
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from this PDF. It may be scanned or image-only."
            )

        context_parts = [
            f"[{name.replace('_', ' ').upper()}]\n{text}"
            for name, text in sections.items()
            if text.strip()
        ]
        context = "\n\n".join(context_parts[:6])

        prompt = f"""You are a legal simplification assistant for Indian citizens.
A citizen has uploaded a bill PDF and asks: {question}

COMPRESSED BILL CONTENT ({title}):
{context}

Answer clearly in simple English. Be concise. Avoid legal jargon."""

    finally:
        os.unlink(tmp_path)



# ---------------------------------------------------------------------------
# POST /trigger-ingest
# ---------------------------------------------------------------------------

@router.post("/trigger-ingest", response_model=IngestResponse)
def trigger_ingest(body: IngestRequest, db: Session = Depends(get_db)):
    """
    - Bill in SQL + ChromaDB  → already_exists
    - Bill in SQL, no Chroma  → re-embed from local PDF
    - Bill not in DB at all   → tell user to wait for scheduler (every 6 hrs)
    """
    bill_number = body.bill_number

    existing = db.query(Bill).filter(
        Bill.bill_number == bill_number,
        Bill.compressed  == True,
    ).first()

    if existing:
        col     = _get_chroma()
        results = col.get(where={"bill_number": bill_number})

        if results["ids"]:
            return IngestResponse(
                status      = "already_exists",
                bill_number = bill_number,
                message     = f"Bill {bill_number} ({existing.title}) is already in the database.",
            )

        log.warning("Bill %s in SQL but missing ChromaDB chunks — re-embedding.", bill_number)
        try:
            from app.ingestion.scheduler import re_embed_bill
            success = re_embed_bill(bill_number)
        except Exception as exc:
            log.error("Re-embed failed for bill %s: %s", bill_number, exc)
            raise HTTPException(status_code=500, detail=f"Re-embedding failed: {str(exc)}")

        if success:
            db.expire_all()
            bill = db.query(Bill).filter(Bill.bill_number == bill_number).first()
            return IngestResponse(
                status      = "ingested",
                bill_number = bill_number,
                message     = (
                    f"Bill {bill_number} ({bill.title if bill else ''}) "
                    f"was re-embedded into the vector store successfully."
                ),
            )
        raise HTTPException(
            status_code=500,
            detail=f"Re-embedding failed for bill {bill_number}. Check server logs."
        )

    log.info("Bill %s not found in DB — user informed to wait for scheduler.", bill_number)
    return IngestResponse(
        status      = "not_found",
        bill_number = bill_number,
        message     = (
            f"Bill {bill_number} is not in the database yet. "
            f"The background scheduler automatically checks the Sansad API for new bills "
            f"every 6 hours and will add it once it becomes available. "
            f"Please check back later."
        ),
    )