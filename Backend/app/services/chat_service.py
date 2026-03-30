def generate_answer(query):
    from app.services.vector_service import search_similar

    chunks = search_similar(query)
    context = "\n".join(chunks)

    return {
        "query": query,
        "context": context[:1000]
    }