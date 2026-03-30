"""
app/ingestion/scheduler.py
==========================
Standalone background ingestion process.

Run from the backend root:
    python -m app.ingestion.scheduler

Pipeline per bill:
    Sansad API -> Download PDF -> Compress (L1-L4)
               -> PostgreSQL (metadata + sections)
               -> ChromaDB (embeddings via all-MiniLM-L6-v2)

LAZY LOADING: chromadb and all heavy model dependencies are imported
ONLY when first used — never at module import time. This keeps the
FastAPI / gunicorn startup instant and memory usage near-zero until
the scheduler actually runs its first poll cycle.
"""

import os
import sys
import tempfile
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# NOTE: Only stdlib + lightweight runtime deps imported at module level.
# chromadb, sentence_transformers (via prompt_compressor), numpy, sklearn
# are ALL deferred to their first point of use.
# ---------------------------------------------------------------------------

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from supabase import create_client, Client

# prompt_compressor itself is safe to import — it is also lazy-loaded.
from app.ingestion.prompt_compressor import compress_pdf_to_json, _get_embed_model
from app.config.database import SessionLocal
from app.models.bill import Bill, BillSection

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL_HOURS: int = int(os.getenv("SCHEDULER_POLL_INTERVAL_HOURS", 6))
BILLS_PER_PAGE:      int = int(os.getenv("SCHEDULER_BILLS_PER_PAGE", 5))
PAGES_TO_CHECK:      int = int(os.getenv("SCHEDULER_PAGES_TO_CHECK", 10))
CHROMA_DIR:          str = os.getenv("CHROMA_DIR", "chroma_db")
CHROMA_COLLECTION:   str = os.getenv("CHROMA_COLLECTION", "bill_sections")
SUPABASE_URL:        str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY:        str = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET:     str = os.getenv("SUPABASE_PDF_BUCKET", "bills")

SANSAD_API_URL = "https://sansad.in/api_rs/legislation/getBills"

DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------------------------------------------------------------------------
# Supabase client — lightweight HTTP client, safe at module level
# ---------------------------------------------------------------------------

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials not set properly")

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("scheduler")

# ---------------------------------------------------------------------------
# ChromaDB lazy singleton
# Typed as Optional[object] so we never import chromadb at module level.
# ---------------------------------------------------------------------------

_chroma_collection: Optional[object] = None


def _get_chroma_collection() -> object:
    """
    Lazily initialise the ChromaDB persistent client and collection.
    chromadb is imported here for the first (and only) time on first call.
    """
    global _chroma_collection
    if _chroma_collection is None:
        import chromadb  # heavy import — lazy
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _chroma_collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("ChromaDB ready: %s (path=%s)", CHROMA_COLLECTION, CHROMA_DIR)
    return _chroma_collection


# ---------------------------------------------------------------------------
# ChromaDB storage
# ---------------------------------------------------------------------------

def _store_in_chroma(
    bill_number: str,
    title:       str,
    year:        str,
    sections:    list[dict],
) -> None:
    """
    Embed each section via all-MiniLM-L6-v2 and upsert into ChromaDB.
    Both the embedding model and the ChromaDB collection are loaded lazily
    on the first invocation of this function.
    """
    collection = _get_chroma_collection()
    model      = _get_embed_model()

    docs:  list[str]  = []
    ids:   list[str]  = []
    metas: list[dict] = []

    for section in sections:
        sec_name = section["section"]
        content  = section["content"].strip()
        if not content:
            continue
        doc_id = f"{bill_number}::{sec_name}"
        docs.append(content)
        ids.append(doc_id)
        metas.append({
            "bill_number": bill_number,
            "section":     sec_name,
            "title":       title,
            "year":        year,
        })

    if not docs:
        log.warning("  Chroma: no non-empty sections to embed for bill %s.", bill_number)
        return

    embeddings = model.encode(docs, batch_size=64, show_progress_bar=False).tolist()  # type: ignore[attr-defined]

    # Upsert: safely delete existing IDs before re-adding
    try:
        existing_result = collection.get(ids=ids)  # type: ignore[attr-defined]
        existing_ids = existing_result.get("ids", [])
        ids_to_delete = [doc_id for doc_id in ids if doc_id in existing_ids]
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)  # type: ignore[attr-defined]
    except Exception as exc:
        log.warning(
            "  Chroma: could not check/delete existing IDs for bill %s: %s",
            bill_number, exc,
        )

    collection.add(  # type: ignore[attr-defined]
        ids        = ids,
        documents  = docs,
        embeddings = embeddings,
        metadatas  = metas,
    )
    log.info("  Chroma: stored %d section embeddings for bill %s.", len(docs), bill_number)


# ---------------------------------------------------------------------------
# Helper: download a PDF from a URL into a temp file
# ---------------------------------------------------------------------------

def _download_temp_pdf(url: str) -> Optional[str]:
    """
    Stream *url* into a NamedTemporaryFile and return its path.
    Caller is responsible for deleting the file after use.
    Returns None on failure.
    """
    for attempt in range(1, 4):
        try:
            log.info("  _download_temp_pdf: attempt %d/3 for %s", attempt, url)
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=180, stream=True)
            resp.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            for chunk in resp.iter_content(chunk_size=65536):
                tmp.write(chunk)
            tmp.flush()
            tmp.close()
            log.info("  _download_temp_pdf: saved to %s", tmp.name)
            return tmp.name
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.warning("  _download_temp_pdf: failed (attempt %d/3): %s", attempt, exc)
            if attempt < 3:
                time.sleep(2)

    log.error("  _download_temp_pdf: gave up after 3 attempts for %s", url)
    return None


# ---------------------------------------------------------------------------
# Re-embed a single bill (SQL exists, ChromaDB missing)
# ---------------------------------------------------------------------------

def re_embed_bill(bill_number: str) -> bool:
    db = SessionLocal()
    try:
        bill = db.query(Bill).filter(Bill.bill_number == bill_number).first()
        if not bill:
            log.error("re_embed_bill: bill %s not found in SQL.", bill_number)
            return False

        stored_url = bill.local_pdf_path
        if not stored_url:
            log.error("re_embed_bill: no PDF URL stored for bill %s.", bill_number)
            return False

        log.info("re_embed_bill: downloading from Supabase URL for bill %s ...", bill_number)
        tmp_path = _download_temp_pdf(stored_url)
        if not tmp_path:
            log.error("re_embed_bill: could not download PDF for bill %s.", bill_number)
            return False

        try:
            log.info("Re-embedding bill %s from temp file %s ...", bill_number, tmp_path)
            result = compress_pdf_to_json(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
                log.info("re_embed_bill: removed temp file %s", tmp_path)
            except OSError as exc:
                log.warning("re_embed_bill: could not remove temp file %s: %s", tmp_path, exc)

        secs = result.get("sections", {})
        if not secs:
            log.error("re_embed_bill: no sections produced for bill %s.", bill_number)
            return False

        sections_list = _sections_to_list(secs)
        _store_in_chroma(
            bill_number = bill_number,
            title       = bill.title or result.get("title", ""),
            year        = str(bill.year or result.get("year", "")),
            sections    = sections_list,
        )

        db.query(BillSection).filter(BillSection.bill_id == bill.id).delete()
        for section in sections_list:
            db.add(BillSection(
                bill_id      = bill.id,
                section_name = section["section"],
                content      = section["content"],
            ))
        db.commit()

        log.info("re_embed_bill: bill %s re-embedded with %d sections.",
                 bill_number, len(sections_list))
        return True

    except SQLAlchemyError as exc:
        db.rollback()
        log.error("re_embed_bill: database error for bill %s: %s", bill_number, exc)
        return False
    except Exception as exc:
        db.rollback()
        log.error("re_embed_bill: failed for bill %s: %s", bill_number, exc)
        return False
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------

def _get_processed_bill_numbers() -> set[str]:
    db = SessionLocal()
    try:
        rows = db.query(Bill.bill_number).filter(Bill.compressed == True).all()
        return {row.bill_number for row in rows}
    finally:
        db.close()


def _persist_to_postgres(
    bill_number:       str,
    title:             str,
    year:              str,
    status:            str,
    ministry_name:     str,
    pdf_url:           str,
    local_pdf_path:    str,
    original_tokens:   int,
    compressed_tokens: int,
    compression_ratio: float,
    sections:          list[dict],
) -> None:
    db  = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        stmt = pg_insert(Bill).values(
            bill_number       = bill_number,
            title             = title,
            year              = year,
            status            = status,
            ministry_name     = ministry_name,
            pdf_url           = pdf_url,
            local_pdf_path    = local_pdf_path,
            compressed        = True,
            original_tokens   = original_tokens,
            compressed_tokens = compressed_tokens,
            compression_ratio = compression_ratio,
            first_seen_at     = now,
            last_seen_at      = now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["bill_number"],
            set_={
                "title":             stmt.excluded.title,
                "year":              stmt.excluded.year,
                "status":            stmt.excluded.status,
                "ministry_name":     stmt.excluded.ministry_name,
                "pdf_url":           stmt.excluded.pdf_url,
                "local_pdf_path":    stmt.excluded.local_pdf_path,
                "compressed":        True,
                "original_tokens":   stmt.excluded.original_tokens,
                "compressed_tokens": stmt.excluded.compressed_tokens,
                "compression_ratio": stmt.excluded.compression_ratio,
                "last_seen_at":      now,
            },
        )
        db.execute(stmt)
        db.flush()

        bill = db.query(Bill).filter(Bill.bill_number == bill_number).one()
        db.query(BillSection).filter(BillSection.bill_id == bill.id).delete()
        for section in sections:
            db.add(BillSection(
                bill_id      = bill.id,
                section_name = section["section"],
                content      = section["content"],
            ))
        db.commit()
        log.info("  PostgreSQL: upserted bill %s with %d sections.", bill_number, len(sections))

    except SQLAlchemyError as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Sansad API
# ---------------------------------------------------------------------------

def _fetch_bills_page(page: int) -> list[dict]:
    params = {
        "loksabha":             "",
        "sessionNo":            "",
        "billName":             "",
        "house":                "Lok Sabha",
        "ministryName":         "",
        "billType":             "Government",
        "billCategory":         "",
        "billStatus":           "",
        "introductionDateFrom": "",
        "introductionDateTo":   "",
        "passedInLsDateFrom":   "",
        "passedInLsDateTo":     "",
        "passedInRsDateFrom":   "",
        "passedInRsDateTo":     "",
        "page":                 page,
        "size":                 BILLS_PER_PAGE,
        "locale":               "en",
        "sortOn":               "billIntroducedDate",
        "sortBy":               "desc",
    }
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                SANSAD_API_URL,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            records = resp.json().get("records", [])
            bills = []
            for item in records:
                bill_number = str(item.get("billNumber", "")).strip()
                if not bill_number:
                    continue
                bills.append({
                    "bill_number":   bill_number,
                    "title":         item.get("billName", "").strip(),
                    "status":        item.get("status", ""),
                    "pdf_url":       item.get("billIntroducedFile", ""),
                    "ministry_name": item.get("ministryName", "").strip(),
                })
            return bills
        except Exception as exc:
            log.warning("API fetch failed (page %d, attempt %d/3): %s", page, attempt, exc)
            if attempt < 3:
                time.sleep(2)
    log.error("API fetch gave up after 3 attempts (page %d).", page)
    return []


# ---------------------------------------------------------------------------
# PDF download -> Supabase Storage
# ---------------------------------------------------------------------------

def _download_pdf(url: str, bill_number: str) -> Optional[str]:
    """
    Download PDF bytes, upload to Supabase Storage, return the public URL.
    No local file is retained after this function returns.
    """
    if not url:
        log.warning("Bill %s has no PDF URL -- skipping.", bill_number)
        return None

    # ---- 1. Fetch PDF bytes with retry ------------------------------------ #
    pdf_bytes: Optional[bytes] = None
    for attempt in range(1, 4):
        try:
            log.info(
                "  Downloading PDF for bill %s (attempt %d/3) ...",
                bill_number, attempt,
            )
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=180, stream=True)
            resp.raise_for_status()
            pdf_bytes = resp.content
            log.info(
                "  Fetched %d KB for bill %s.",
                len(pdf_bytes) // 1024, bill_number,
            )
            break
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.warning(
                "  Download failed for bill %s (attempt %d/3): %s",
                bill_number, attempt, exc,
            )
            if attempt < 3:
                time.sleep(2)

    if not pdf_bytes:
        log.error("  Download gave up after 3 attempts for bill %s.", bill_number)
        return None

    # ---- 2. Upload to Supabase Storage with retry ------------------------- #
    storage_path = f"{bill_number}.pdf"
    for attempt in range(1, 4):
        try:
            log.info(
                "  Uploading bill %s to Supabase bucket '%s' (attempt %d/3) ...",
                bill_number, SUPABASE_BUCKET, attempt,
            )
            _supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=storage_path,
                file=pdf_bytes,
                file_options={
                    "content-type": "application/pdf",
                    "upsert":       "true",
                },
            )
            break
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.warning(
                "  Supabase upload failed for bill %s (attempt %d/3): %s",
                bill_number, attempt, exc,
            )
            if attempt < 3:
                time.sleep(2)
    else:
        log.error(
            "  Supabase upload gave up after 3 attempts for bill %s.", bill_number,
        )
        return None

    # ---- 3. Return public URL --------------------------------------------- #
    public_url: str = _supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
    log.info("  Supabase public URL for bill %s: %s", bill_number, public_url)
    return public_url


# ---------------------------------------------------------------------------
# Section dict -> list
# ---------------------------------------------------------------------------

def _sections_to_list(sections: dict) -> list[dict]:
    return [
        {"section": name, "content": text}
        for name, text in sections.items()
        if text and text.strip()
    ]


# ---------------------------------------------------------------------------
# Core poll cycle
# ---------------------------------------------------------------------------

def poll_and_ingest() -> None:
    log.info("=" * 60)
    log.info("POLL CYCLE STARTED - %s", datetime.now(timezone.utc).isoformat())
    log.info("=" * 60)

    processed = _get_processed_bill_numbers()
    log.info("Bills already in DB: %d", len(processed))

    ingested = 0

    for page in range(1, PAGES_TO_CHECK + 1):
        log.info("Fetching page %d / %d ...", page, PAGES_TO_CHECK)
        bills = _fetch_bills_page(page)

        if not bills:
            log.info("  Empty page -- stopping early.")
            break

        for bill in bills:
            bill_number = bill["bill_number"]
            api_title   = bill["title"]

            if bill_number in processed:
                log.info("  [SKIP] %s -- already processed.", bill_number)
                continue

            log.info("  [NEW]  %s -- %s", bill_number, api_title)

            # Returns Supabase public URL (or None on failure)
            public_url = _download_pdf(bill["pdf_url"], bill_number)
            if not public_url:
                continue

            # Compression still needs a real file on disk; use a temp file
            tmp_path = _download_temp_pdf(public_url)
            if not tmp_path:
                log.error(
                    "  Could not download temp PDF for compression: bill %s", bill_number,
                )
                continue

            try:
                log.info("  Compressing bill %s ...", bill_number)
                result = compress_pdf_to_json(tmp_path)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log.error("  Compression failed for bill %s: %s", bill_number, exc)
                continue
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            orig  = result.get("original_tokens", 0)
            comp  = result.get("compressed_tokens", 0)
            ratio = result.get("compression_ratio", 0.0)
            secs  = result.get("sections", {})
            title = result.get("title") or api_title
            year  = result.get("year", "")

            log.info(
                "  Compression: %dx | %d -> %d tokens | title: %s | sections: %s",
                int(ratio), orig, comp, title, list(secs.keys()),
            )

            sections_list = _sections_to_list(secs)
            if not sections_list:
                log.warning("  No usable sections for bill %s -- skipping.", bill_number)
                continue

            try:
                _store_in_chroma(
                    bill_number = bill_number,
                    title       = title,
                    year        = year,
                    sections    = sections_list,
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log.error("  ChromaDB storage failed for bill %s: %s", bill_number, exc)
                continue

            try:
                _persist_to_postgres(
                    bill_number       = bill_number,
                    title             = title,
                    year              = year,
                    status            = bill["status"],
                    ministry_name     = bill["ministry_name"],
                    pdf_url           = bill["pdf_url"],
                    local_pdf_path    = public_url,
                    original_tokens   = orig,
                    compressed_tokens = comp,
                    compression_ratio = ratio,
                    sections          = sections_list,
                )
            except KeyboardInterrupt:
                raise
            except SQLAlchemyError as exc:
                log.error("  PostgreSQL persist failed for bill %s: %s", bill_number, exc)
                continue

            processed.add(bill_number)
            ingested += 1
            log.info(
                "  [DONE] bill %s | %.1fx compression | %d sections | title: %s",
                bill_number, ratio, len(sections_list), title,
            )

        time.sleep(3)

    log.info("POLL CYCLE DONE -- %d new bills ingested.", ingested)
    log.info("Next poll in %d hour(s).", POLL_INTERVAL_HOURS)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Scheduler startup
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """
    Start the blocking APScheduler loop.

    IMPORTANT: This function (and the initial poll_and_ingest() call inside it)
    is the ONLY place where heavy computation is triggered.  FastAPI should
    NOT call this at import time.  Start the scheduler in a background thread
    or a separate worker process, or via an explicit startup event if needed.

    Example (FastAPI lifespan — opt-in):
        import threading
        from app.ingestion.scheduler import start_scheduler

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            t = threading.Thread(target=start_scheduler, daemon=True)
            t.start()
            yield
    """
    log.info("Scheduler service starting up ...")
    log.info("Running initial poll on startup ...")
    poll_and_ingest()   # <-- heavy work begins here, never at import time

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        poll_and_ingest,
        trigger="interval",
        hours=POLL_INTERVAL_HOURS,
        id="sansad_poll",
        max_instances=1,
        coalesce=True,
    )

    log.info(
        "Scheduler running -- polling every %d hour(s). Ctrl-C to stop.",
        POLL_INTERVAL_HOURS,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


# ---------------------------------------------------------------------------
# Entry point — only triggers heavy work when run as __main__
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    start_scheduler()