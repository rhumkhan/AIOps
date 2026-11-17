"""AIOps Platform — REST API."""

from fastapi import FastAPI

try:  # Supports both Docker's ``main:app`` and local ``api.main:app`` imports.
    from .incidents import router as incidents_router
    from .otlp import router as otlp_router
except ImportError:
    from incidents import router as incidents_router
    from otlp import router as otlp_router

app = FastAPI(
    title="AIOps Platform",
    description="Application-agnostic AIOps platform API.",
    version="0.1.0",
)

app.include_router(otlp_router)
app.include_router(incidents_router)


@app.get("/health")
async def health():
    """Liveness check. Returns 200 if the API process is running."""
    return {"status": "healthy"}
