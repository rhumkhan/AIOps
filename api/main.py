"""AIOps Platform — REST API."""

from fastapi import FastAPI

app = FastAPI(
    title="AIOps Platform",
    description="Application-agnostic AIOps platform API.",
    version="0.1.0",
)


@app.get("/health")
async def health():
    """Liveness check. Returns 200 if the API process is running."""
    return {"status": "healthy"}
