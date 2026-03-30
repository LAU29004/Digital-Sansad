import logging

log = logging.getLogger("vector_service")

CHROMA_DIR  = "chroma_db"
COLLECTION  = "bill_sections"
EMBED_MODEL = "all-MiniLM-L6-v2"

_client     = None
_collection = None
_model: object | None = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        import chromadb
        _client     = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_or_create_collection(name=COLLECTION)
    return _collection


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        log.info("Loading embedding model...")
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed_and_store_sections(
    bill_id:  str,
    title:    str,
    year:     str,
    sections: list[dict],
) -> None:
    collection = _get_collection()
    model      = _get_model()

    docs, ids, metas = [], [], []

    for section in sections:
        sec_name = section["section"]
        content  = section["content"]
        if not content.strip():
            continue

        doc_id = f"{bill_id}::{sec_name}"

        try:
            collection.delete(ids=[doc_id])
        except Exception:
            pass

        docs.append(content)
        ids.append(doc_id)
        metas.append({
            "bill_id": str(bill_id),
            "section": sec_name,
            "title":   title,
            "year":    year,
        })

    if not docs:
        log.warning("No non-empty sections to embed for bill %s", bill_id)
        return

    embeddings = model.encode(docs).tolist()
    collection.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
    log.info("Stored %d sections in Chroma for bill %s", len(docs), bill_id)


def search_similar(query: str, n_results: int = 5) -> list[str]:
    collection = _get_collection()
    model      = _get_model()

    embedding = model.encode([query]).tolist()
    results   = collection.query(query_embeddings=embedding, n_results=n_results)

    return results["documents"][0] if results["documents"] else []