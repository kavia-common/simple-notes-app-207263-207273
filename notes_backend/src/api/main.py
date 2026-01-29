"""FastAPI entrypoint for notes_backend.

Exposes:
- Health check
- Notes CRUD endpoints

Environment:
- SQLITE_DB: absolute/relative path to the SQLite database file created by notes_database.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.db import ensure_schema
from src.api.notes import router as notes_router

openapi_tags = [
    {
        "name": "health",
        "description": "Health and service status endpoints.",
    },
    {
        "name": "notes",
        "description": "CRUD operations for notes.",
    },
]

app = FastAPI(
    title="Simple Notes Backend API",
    description="Backend REST API for a simple notes app (no authentication).",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

# CORS: allow React frontend to call the API. For production, restrict this to your
# deployed frontend origin(s). For this coding task, allow all origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure schema exists on startup (safe to run multiple times).
@app.on_event("startup")
async def _startup() -> None:
    ensure_schema()


@app.get(
    "/",
    tags=["health"],
    summary="Health check",
    description="Basic health check endpoint to verify the API is running.",
    operation_id="health_check",
)
def health_check():
    """Health check endpoint.

    Returns:
        JSON object indicating service is healthy.
    """
    return {"message": "Healthy"}


app.include_router(notes_router)
