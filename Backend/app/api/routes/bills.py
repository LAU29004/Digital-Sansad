from fastapi import APIRouter

router = APIRouter()

@router.post("/")
def chat(query: str):
    from app.services.chat_service import generate_answer
    return generate_answer(query)