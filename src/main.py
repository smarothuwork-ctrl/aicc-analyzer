from __future__ import annotations

from fastapi import FastAPI

from src.api.routes.health import router as health_router

app = FastAPI(title="AICC Analyzer")
app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AICC Analyzer service is running"}
