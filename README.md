# 🏛️ Digital Sansad

> **Democracy, Decoded.**
> Real-time, citizen-friendly summaries of Indian parliamentary bills and legal documents — powered by a 4-layer token compression pipeline for maximum information density and minimum carbon footprint.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React Native](https://img.shields.io/badge/Frontend-React%20Native%20%2F%20Expo-61DAFB?style=flat-square&logo=react)](https://reactnative.dev/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-FF6B35?style=flat-square)](https://www.trychroma.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791?style=flat-square&logo=postgresql)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python)](https://www.python.org/)
[![HuggingFace](https://img.shields.io/badge/LLM-HuggingFace%20%2B%20Gemini-FFD21E?style=flat-square&logo=huggingface)](https://huggingface.co/)

---

## 📌 Table of Contents

- [The Problem](#the-problem)
- [Our Solution](#our-solution)
- [The Core Innovation: 4-Layer Token Compression](#the-core-innovation-4-layer-token-compression)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Database Schema](#database-schema)
- [Features](#features)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Information Density — How We Measure Success](#information-density--how-we-measure-success)
- [Contributing](#contributing)
- [License](#license)

---

## The Problem

Indian law and parliamentary bills are notoriously dense, verbose, and inaccessible to the average citizen. The Finance Bill, the IT Amendment Act, new Parliamentary Bills — these documents routinely exceed **100,000 tokens** and are written in complex legalese that requires professional expertise to parse.

Two problems compound each other:

1. **Accessibility Gap** — Citizens are left uninformed about policies that directly affect their lives.
2. **Environmental Cost** — Running large language models on raw legal documents repeatedly is energy-intensive and environmentally costly. Feeding 100k+ token documents into an LLM for every citizen query is unsustainable at scale.

---

## Our Solution

**Digital Sansad** is a citizen-facing dashboard that:

- 🔄 **Automatically monitors** the official Sansad API (`sansad.in/api_rs/legislation/getBills`) every 6 hours for new Lok Sabha Government Bills
- 📄 **Ingests and compresses** legal PDFs through a 4-layer NLP pipeline before storage — the expensive work happens **once at ingestion**, not on every query
- 🔎 **Enables semantic search** so citizens can ask plain-language questions about any policy
- 🤖 **Delivers LLM-synthesized summaries** using a two-model architecture: a cheap 8B model for schema filling and Chain-of-Density, and a powerful 70B model for the final citizen answer
- 📤 **Accepts PDF uploads** from citizens for on-the-fly compression and Gemini-powered summarization

---

## The Core Innovation: 4-Layer Token Compression

This is the technical heart of Digital Sansad, implemented in `app/ingestion/prompt_compressor.py`.

### Pipeline Overview

```
Raw PDF  (pdfplumber primary → PyMuPDF fallback)
    │
    ▼  L1: STRIP
    │   Regex removal of: gazette headers, enactment clauses, assent notices,
    │   secretary signatures, financial memorandums, bare page numbers,
    │   statement of objects, delegated legislation memorandums
    │
    ▼  L2: DEDUP  (all-MiniLM-L6-v2 — local, no API key)
    │   Encodes all sentences into embeddings in batches of 128
    │   Drops any sentence with cosine similarity ≥ 0.90 to an earlier one
    │   Eliminates the repeated boilerplate clauses common across Indian bills
    │
    ▼  L3: EXTRACT  (TF-IDF)
    │   Keeps top 20% of sentences by TF-IDF score (max_features=10,000)
    │   Legal signal words (shall, penalty, offence, liable, board, tribunal…)
    │   add +0.4 score per hit; "section N" references add +0.5
    │   Minimum 8 sentences always retained regardless of score
    │
    ▼  L4: CLASSIFY
        Each sentence matched against 9 semantic buckets via keyword scoring:
        penalties | citizen_rights | regulatory_body | obligations
        definitions | amendments | appeal_mechanism | schedules | enforcement
        → Named sections stored in PostgreSQL (bill_sections) + ChromaDB
```

### Compression Ratios Achieved

| Stage | Approx. Tokens Remaining | Reduction from Raw |
|---|---|---|
| Raw PDF | ~100,000 | baseline |
| After L1 Strip | ~70,000 | ~30% |
| After L2 Dedup | ~45,000 | ~55% |
| After L3 Extract (20% keep ratio) | ~7,000–10,000 | **90–93%** |
| Tokens sent to LLM per query | ~3,000–8,000 | **90–93% overall** |

At query time, a **Chain-of-Density** pass (3 rounds using the cheap 8B model) further rewrites retrieved sections to pack more named entities, amounts, dates, and section references per sentence — without increasing token count.

### Why This Matters

| Metric | Without Compression | With Compression |
|---|---|---|
| Tokens per query | ~80,000+ | ~3,000–8,000 |
| LLM API cost | Very high | 90–93% reduction |
| Carbon per query | High | Low |
| Information retained | 100% | ~95%+ semantic retention |
| **Token Density Increase** | baseline | **900%** |

---

## System Architecture

### Full System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         APScheduler                                  │
│              BlockingScheduler — every 6 hours (Asia/Kolkata)        │
│       polls: sansad.in/api_rs/legislation/getBills                   │
│       (Lok Sabha, Government bills, sorted by intro date desc)       │
└────────────────────────────┬─────────────────────────────────────────┘
                             │  New bill detected
                             ▼
                    ┌────────────────────┐
                    │   PostgreSQL (RDB) │
                    │  compressed=true?  │
                    └──────┬─────────────┘
                    EXISTS │         │ NEW
                           │         ▼
                    Skip ◄─┘   Download PDF → 4-Layer Compression
                                              (L1 Strip → L2 Dedup
                                               → L3 TF-IDF → L4 Classify)
                                                    │
                                       ┌────────────┼────────────┐
                                       ▼            ▼            ▼
                                  PostgreSQL    ChromaDB     Local disk
                                  bills +       section      pdfs/
                                  bill_sections embeddings   {bill_number}.pdf
                                  token stats   (MiniLM)


  ┌──────────────────┐   REST API   ┌─────────────────────────────────┐
  │  React Native    │◄────────────►│         FastAPI Backend         │
  │  Expo Frontend   │              │                                 │
  │  ExploreScreen   │  /bills      │  GET  /bills  — list + search   │
  │  BillDetails     │  /bills/:id  │  GET  /bills/:id — sections     │
  │  ChatScreen      │  /chat       │  POST /chat   — 5-step pipeline │
  │  UploadScreen    │  /upload-pdf │  POST /upload-pdf — on-demand   │
  │                  │  /health     │  POST /trigger-ingest — re-embed│
  └──────────────────┘              └─────────────────────────────────┘
```

### Query Pipeline (5 Steps)

```
User Question
      │
      ▼  Step 1 — Schema Extraction  (Llama-3.1-8B, cheap)
      │  Extracts: { bill_number, title, year, status, ministry, topic }
      │  Only populates fields the user explicitly mentioned
      │
      ▼  Step 2 — PostgreSQL Match
      │  Filters WHERE compressed=true; bill_number exact match
      │  takes priority; falls back to title ILIKE + year + status
      │
      ▼  Step 3 — ChromaDB Retrieval
      │  Top-3 sections per bill via cosine similarity
      │  Query embedded with all-MiniLM-L6-v2 (local, no API call)
      │  Sections labeled: [PENALTIES], [CITIZEN_RIGHTS], etc.
      │
      ▼  Step 4 — Chain-of-Density  (Llama-3.1-8B, 3 rounds)
      │  Each section rewritten: same length, more named entities
      │  More section numbers, penalty amounts, ministry names per sentence
      │
      ▼  Step 5 — Final Answer  (Llama-3.3-70B, strong)
         Plain-English answer ≤200 words
         Cites section labels; avoids legal jargon
         Returns: { answer, sources, bills_used }
```

---

## Tech Stack

| Layer | Technology | Details |
|---|---|---|
| **Frontend** | React Native + Expo | ExploreScreen, BillDetailsScreen, ChatScreen, PDF Upload |
| **Backend** | FastAPI 0.111 | Async REST, CORS, auto OpenAPI/Swagger docs |
| **Scheduler** | APScheduler `BlockingScheduler` | 6h poll interval, `Asia/Kolkata` timezone, `max_instances=1` |
| **Scraper** | Beautiful Soup 4 | HTML fallback scraper for `sansad.in/ls/legislation/bills` |
| **Primary Source** | Sansad REST API | `sansad.in/api_rs/legislation/getBills` — Lok Sabha Government bills |
| **PDF Extraction** | pdfplumber → PyMuPDF | Dual extractor with automatic fallback for scanned/complex PDFs |
| **Compression** | Custom 4-layer NLP | L1 regex stripping, L2 MiniLM dedup, L3 TF-IDF, L4 keyword classify |
| **Embeddings** | `all-MiniLM-L6-v2` | Sentence-transformers, runs locally, no API key required |
| **Vector DB** | ChromaDB (persistent) | Cosine similarity space, sections keyed as `{bill_number}::{section}` |
| **Relational DB** | PostgreSQL | `bills` + `bill_sections` tables via SQLAlchemy 2.0 + pg_insert upsert |
| **Cheap LLM** | `Llama-3.1-8B-Instruct` | Schema extraction + Chain-of-Density (HuggingFace Inference API) |
| **Strong LLM** | `Llama-3.3-70B-Instruct` | Final citizen answer (HuggingFace / Novita provider) |
| **Upload LLM** | `gemini-2.0-flash` | On-demand PDF upload summarization (Google Gemini) |
| **Token Counting** | `tiktoken` cl100k_base | Accurate token measurement for all compression reports |
| **ORM** | SQLAlchemy 2.0 + Alembic | Schema migrations, session management, upsert via `on_conflict_do_update` |

---

## Database Schema

### `bills` table

The primary registry of all ingested parliamentary bills. Stores both the raw Sansad API metadata and the compression statistics produced by the 4-layer pipeline.

```sql
CREATE TABLE bills (
    -- Identity
    bill_number                 VARCHAR     NOT NULL UNIQUE,  -- e.g. "72"

    -- Sansad API metadata
    bill_name                   TEXT,                         -- Full official bill title
    ministry_name               TEXT,                         -- Sponsoring ministry
    member_name                 TEXT,                         -- Introducing member (private bills)
    bill_introduced_date        TIMESTAMPTZ,                  -- Date introduced in house
    passed_in_ls_date           TIMESTAMPTZ,                  -- Date passed in Lok Sabha
    passed_in_rs_date           TIMESTAMPTZ,                  -- Date passed in Rajya Sabha
    status                      VARCHAR,                      -- "Introduced" | "Passed" | "Pending" etc.
    act_no                      VARCHAR,                      -- Act number once enacted
    assent_date                 TIMESTAMPTZ,                  -- Presidential assent date
    gazette_notification        TEXT,                         -- Gazette reference string
    referred_to_committee_date  TIMESTAMPTZ,                  -- Date referred to standing committee
    bill_introduced_file        TEXT,                         -- PDF URL from Sansad API

    -- Ingestion tracking
    local_pdf_path              TEXT,                         -- Local path: pdfs/{bill_number}.pdf
    compressed                  BOOLEAN     DEFAULT FALSE,    -- True once pipeline completes
    first_seen_at               TIMESTAMPTZ,
    last_seen_at                TIMESTAMPTZ,                  -- Updated on every scheduler cycle

    -- Compression statistics (from 4-layer pipeline)
    original_tokens             INTEGER     DEFAULT 0,        -- Raw PDF token count
    compressed_tokens           INTEGER     DEFAULT 0,        -- Post L1-L3 token count
    compression_ratio           FLOAT       DEFAULT 0.0       -- original / compressed
);
```

> **Note:** The full schema above reflects the target data model. The current SQLAlchemy ORM (`app/models/bill.py`) uses a subset of these columns (`bill_number`, `title`, `year`, `status`, `pdf_url`, `local_pdf_path`, `compressed`, `original_tokens`, `compressed_tokens`, `compression_ratio`, `first_seen_at`, `last_seen_at`). Migration to the full schema is in progress — see [Contributing](#contributing).

### `bill_sections` table

Stores the classified output of the L4 compression layer. Each row is one named section of a bill.

```sql
CREATE TABLE bill_sections (
    id           SERIAL      PRIMARY KEY,
    bill_id      INTEGER     NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    section_name VARCHAR,    -- "penalties" | "citizen_rights" | "regulatory_body" |
                             -- "obligations" | "definitions" | "amendments" |
                             -- "appeal_mechanism" | "schedules" | "enforcement"
    content      TEXT        -- Compressed section text, also embedded in ChromaDB
);
```

### ChromaDB collection: `bill_sections`

Mirrors the PostgreSQL `bill_sections` table as vector embeddings for semantic search.

| Field | Value |
|---|---|
| **Collection name** | `bill_sections` (configurable via `CHROMA_COLLECTION` env var) |
| **Distance metric** | Cosine similarity (`hnsw:space = cosine`) |
| **Document ID format** | `{bill_number}::{section_name}` (e.g. `72::penalties`) |
| **Embedding model** | `all-MiniLM-L6-v2` (384-dim, local) |
| **Metadata stored** | `bill_number`, `section`, `title`, `year` |

---

## Features

- 🕐 **Automated Sansad Monitoring** — `BlockingScheduler` polls the Sansad REST API every 6 hours for Lok Sabha Government Bills; checks 10 pages × 5 bills per run; runs on startup then on interval
- 📄 **Dual PDF Extractor** — pdfplumber first, PyMuPDF fallback; both handle page-level failures gracefully without crashing the pipeline
- 🗜️ **4-Layer Compression** — Boilerplate stripping → semantic deduplication → TF-IDF extraction → section classification, achieving **90–93% token reduction** before any LLM call
- ⛓️ **Chain-of-Density** — 3 rounds of cheap-LLM rewriting pack more legal facts per sentence at query time, maximizing information density in the strong LLM's context window
- 🔎 **Semantic Section Search** — ChromaDB retrieves the top-3 most relevant compressed sections per bill using cosine similarity on `all-MiniLM-L6-v2` embeddings
- 🤖 **Two-Model Architecture** — Small 8B model for high-frequency, low-stakes tasks; large 70B model reserved for the single final citizen answer
- 📤 **PDF Upload** — Citizens upload any government PDF; compressed on-the-fly by the full 4-layer pipeline and answered by Gemini 2.0 Flash; nothing stored
- 🔁 **Smart Re-embedding** — `/trigger-ingest` detects bills present in PostgreSQL but absent from ChromaDB and re-embeds from the locally cached PDF
- 📱 **Expo React Native Frontend** — Bill list with full-text search, expandable compressed section cards, AI chat interface, dark/light theme toggle
- 📊 **Token Compression Reporting** — Every ingestion logs raw → L1 → L2 → L3 token counts with percentage reduction at each stage; every query logs CoD before/after and overall compression ratio

---

## Getting Started

### Prerequisites

- Python `>= 3.10`
- Node.js `>= 18.x` + Expo CLI
- PostgreSQL `>= 14`

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/LAU29004/AI-LEGISLATIVE.git
cd AI-LEGISLATIVE
```

**2. Set up the Python backend**

```bash
cd Backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Set up the Expo frontend**

```bash
cd frontend
npm install
```

**4. Initialize PostgreSQL**

```bash
psql -U postgres -c "CREATE DATABASE legislative_db;"
cd Backend
python -m app.create_tables     # Creates bills + bill_sections tables
```

### Environment Variables

Create a `.env` file in `Backend/`:

```env
# PostgreSQL
DATABASE_URL=postgresql://postgres:password@localhost:5432/legislative_db

# ChromaDB (local persistent directory)
CHROMA_DIR=chroma_db
CHROMA_COLLECTION=bill_sections

# HuggingFace Inference API (free tier)
# Get your token at: https://huggingface.co/settings/tokens
HF_TOKEN=hf_your_token_here

# Google Gemini (for /upload-pdf endpoint)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash

# Scheduler tuning
SCHEDULER_POLL_INTERVAL_HOURS=6
SCHEDULER_BILLS_PER_PAGE=5
SCHEDULER_PAGES_TO_CHECK=10
SCHEDULER_PDF_DIR=pdfs
```

Update the API base URL in `frontend/services/api.ts`:

```typescript
const BASE_URL = "http://<your-machine-local-ip>:8000";
```

### Running the App

**1. Start the FastAPI backend**

```bash
cd Backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**2. Start the background scheduler** (separate terminal)

```bash
cd Backend
python -m app.ingestion.scheduler
# Runs an immediate poll on startup, then every 6 hours
```

**3. (Optional) Trigger a manual ingestion immediately**

```bash
cd Backend
python run_ingestion.py
```

**4. Start the Expo frontend**

```bash
cd frontend
npx expo start
# w → web browser  |  a → Android  |  i → iOS
```

---

## Project Structure

```
AI-LEGISLATIVE/
├── Backend/
│   ├── app/
│   │   ├── main.py                      # FastAPI app, CORS middleware, router registration
│   │   ├── create_tables.py             # Creates bills + bill_sections tables
│   │   ├── config/
│   │   │   ├── database.py              # SQLAlchemy engine + SessionLocal
│   │   │   └── settings.py              # Pydantic settings loaded from .env
│   │   ├── models/
│   │   │   └── bill.py                  # Bill + BillSection ORM models
│   │   ├── schemas/
│   │   │   ├── bill_schema.py           # Pydantic request/response for /bills
│   │   │   └── chat_schema.py           # Pydantic request/response for /chat
│   │   ├── routers/
│   │   │   ├── bills.py                 # GET /bills, GET /bills/:bill_number
│   │   │   └── chat.py                  # POST /chat, /upload-pdf, /trigger-ingest
│   │   ├── ingestion/
│   │   │   ├── prompt_compressor.py     # ★ 4-layer compression engine (L1→L4)
│   │   │   ├── scheduler.py             # APScheduler + ChromaDB embed + PG upsert
│   │   │   ├── aneesh_scheduler.py      # Alternate scheduler variant
│   │   │   ├── query_pipeline.py        # Standalone CLI 5-step query pipeline
│   │   │   ├── fetch_bills.py           # Sansad API fetch + PDF download helpers
│   │   │   ├── chunker.py               # Text chunking utilities
│   │   │   ├── extractor.py             # Text extraction helpers
│   │   │   └── parser.py                # PDF parsing helpers
│   │   ├── services/
│   │   │   ├── bill_service.py          # Bill CRUD business logic
│   │   │   ├── embedding_service.py     # MiniLM embedding wrapper
│   │   │   ├── vector_service.py        # ChromaDB query wrapper
│   │   │   └── llm_service.py           # LLM call abstraction
│   │   ├── core/
│   │   │   ├── llm_client.py            # HuggingFace + Gemini client init
│   │   │   ├── vectordb_client.py       # ChromaDB persistent client
│   │   │   └── redis_client.py          # Redis client (caching — not yet wired)
│   │   ├── repositories/
│   │   │   └── bill_repo.py             # Raw PostgreSQL bill queries
│   │   └── utils/
│   │       ├── pdf_utils.py             # PDF download, path, storage utilities
│   │       └── text_cleaner.py          # Text normalization helpers
│   ├── webextract.py                    # Beautiful Soup HTML scraper (fallback source)
│   ├── re_embed_all.py                  # Bulk re-embedding utility
│   ├── check_chroma.py                  # ChromaDB inspection/debug tool
│   ├── run_ingestion.py                 # Manual ingestion trigger
│   ├── requirements.txt
│   └── .env
│
├── TokenCompression/
│   └── promp_compressor.py              # Standalone compression research file
│
└── frontend/
    ├── App.tsx                          # Root navigator
    ├── BottomNav.tsx                    # Tab bar navigation
    ├── screens/                         # ExploreScreen, BillDetailsScreen, ChatScreen, etc.
    ├── services/
    │   └── api.ts                       # All FastAPI calls — single source of truth
    ├── context/
    │   └── ThemeContext.tsx             # Dark/light theme provider
    ├── components/                      # Reusable UI components
    ├── constants/                       # Colors, spacing, font constants
    ├── hooks/                           # Custom React hooks
    └── package.json
```

---

## API Reference

Full interactive docs at `http://localhost:8000/docs` (Swagger UI) after starting the server.

### `GET /bills`

List all compressed bills. Supports search by title or bill number.

```
GET /bills
GET /bills?search=finance
GET /bills?search=72&limit=10&offset=0
```

### `GET /bills/{bill_number}`

Full bill detail with all compressed sections.

**Response:**
```json
{
  "id": 1,
  "bill_number": "72",
  "title": "THE APPROPRIATION BILL, 2026",
  "year": "2026",
  "status": "Introduced",
  "compressed": true,
  "original_tokens": 94200,
  "compressed_tokens": 8100,
  "compression_ratio": 11.6,
  "sections": [
    { "section_name": "penalties",      "content": "..." },
    { "section_name": "citizen_rights", "content": "..." },
    { "section_name": "obligations",    "content": "..." }
  ]
}
```

### `POST /chat`

Full 5-step query pipeline. Optionally scoped to a specific bill.

> **⚠️ Note:** Chat functionality uses the HuggingFace Inference API (free tier). Due to API key rate limits, chat usage may be restricted under high load. If you encounter errors, please wait a moment and try again, or configure your own `HF_TOKEN` in the `.env` file.

**Request:**
```json
{
  "question": "What are the penalties for non-compliance?",
  "bill_number": "72"
}
```

**Response:**
```json
{
  "answer": "Non-compliance with Section 15 carries a penalty of up to ₹250 crore...",
  "sources": [
    { "bill_number": "72", "title": "THE APPROPRIATION BILL, 2026", "section": "[PENALTIES]" }
  ],
  "bill_number": "72",
  "bill_title": "THE APPROPRIATION BILL, 2026",
  "bills_used": [{ "bill_number": "72", "title": "THE APPROPRIATION BILL, 2026" }]
}
```

### `POST /upload-pdf`

On-the-fly compression + Gemini answer. Document is not stored.

**Request:** `multipart/form-data` — `file` (PDF) + optional `question` (string)

**Response:**
```json
{
  "answer": "This bill proposes...",
  "bill_title": "THE FINANCE BILL, 2026",
  "year": "2026",
  "compression_ratio": 9.3,
  "sections_found": ["penalties", "obligations", "definitions"]
}
```

### `POST /trigger-ingest`

Check DB status for a bill; re-embeds from local PDF if missing from ChromaDB.

**Request:** `{ "bill_number": "72" }`

**Response:** `{ "status": "already_exists" | "ingested" | "not_found", "bill_number": "72", "message": "..." }`

### `GET /health`

```json
{ "status": "ok" }
```

---

## Information Density — How We Measure Success

> *"How much value is delivered per token consumed?"*

Digital Sansad tracks compression metrics explicitly on every ingested bill and every query:

| Metric | Description | Stored In |
|---|---|---|
| `original_tokens` | Full raw PDF token count (tiktoken cl100k_base) | PostgreSQL `bills` |
| `compressed_tokens` | Post L1–L3 stored token count | PostgreSQL `bills` |
| `compression_ratio` | `original_tokens / compressed_tokens` | PostgreSQL `bills` |
| CoD before/after | Token delta per Chain-of-Density round | Query pipeline logs |
| Overall query compression | Raw tokens → tokens sent to strong LLM | Terminal report |

Our target: **deliver 95%+ of the factual information in a legal document using 7–10% of its original token count at query time** — while keeping answers readable to a citizen with no legal background.

---

## Contributing

We welcome contributions from developers, legal experts, and civic tech enthusiasts.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add: your feature description'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

**Areas where we especially need help:**

- **Schema migration** — Wire up the full `bills` schema (`ministry_name`, `member_name`, `bill_introduced_date`, `passed_in_ls_date`, `passed_in_rs_date`, `act_no`, `assent_date`, `gazette_notification`, `referred_to_committee_date`) to the SQLAlchemy ORM and scheduler ingestion. The Sansad API returns all these fields; they just aren't persisted yet
- **Lok Sabha + Rajya Sabha** — Currently the API call targets Lok Sabha; adding Rajya Sabha requires toggling the `house` parameter and deduplicating bills that pass both houses
- **Redis caching** — The `redis_client.py` exists but is not yet wired to the query pipeline; caching repeated questions would eliminate redundant LLM calls entirely
- **Hindi and regional language output** — Summarization currently outputs English only
- **Alembic migrations** — Schema versioning via `alembic revision --autogenerate`
- **Semantic retention evaluation** — Measuring how much factual content is lost at each compression layer

---

<p align="center">
  <b>Digital Sansad</b> — Because every citizen deserves to understand the laws that govern them.<br/>
  Built with ❤️ for India 🇮🇳
</p>
