import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from qlink_chatbot.routes.dashboard_routes import dashboard_router
from qlink_chatbot.routes.general_routes import general_router
from qlink_chatbot.routes.whatsapp_routes import whatsapp_router
from qlink_chatbot.routes.ws_routes import ws_router
from qlink_chatbot.database.mongo_utils import init_system_prompt
from qlink_chatbot.utils.logger_config import logger

_DEFAULT_CORS_ORIGINS = [
    "https://jaipurrugs.claraai.tech",
    "https://jaipurrugs-bot.vercel.app",
    "https://jaipurrugs-kj8bpr4k4-qlink149s-projects.vercel.app",
    "https://qlink-jr.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]


def _get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    for default in _DEFAULT_CORS_ORIGINS:
        if default not in origins:
            origins.append(default)
    return origins or ["*"]


app = FastAPI(
    title="Jaipur Rugs chatbot backend API",
    version="0.1.0",
    redoc_url=None,
    docs_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(general_router, prefix="/api/web")
app.include_router(ws_router)
app.include_router(whatsapp_router)


@app.get("/ping")
def ping():
    logger.info("Ping endpoint called")
    return {"message": "Jaipur Rugs chatbot backend API is up and running"}


init_system_prompt()
logger.info("Jaipur Rugs backend initialized successfully.")
