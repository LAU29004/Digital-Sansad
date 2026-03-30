import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import bills, chat
from app.ingestion.scheduler import start_scheduler  
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("RUN_SCHEDULER", "false").lower() == "true":
        thread = threading.Thread(target=start_scheduler, daemon=True)
        thread.start()
    yield

app = FastAPI(
    title="Legislative AI API",
    description="AI-powered Indian legislative bill analysis",
    version="1.0.0",
    lifespan=lifespan,  
)
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bills.router, prefix="/bills", tags=["bills"])
app.include_router(chat.router, tags=["chat"])


@app.get("/health")
def health():
    return {"status": "ok"}
