"""
Main application module for AICC Analyzer service.

This module initializes the FastAPI application, configures settings,
and registers API routes for the contract compliance evaluation analyzer.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.settings import get_settings

# Initialize settings
settings = get_settings()

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Orchestrator for contract compliance evaluation",
    # root_path is used when the application runs behind a reverse proxy
    # e.g., Nginx, or AWS ALB that strips the context path prefix. This ensures
    # - OpenAPI docs (/docs) generate correct URLs with the full path
    # - Link headers and redirects include the proxy prefix
    # - OAuth2 redirect URIs are correctly formed
    # Example: If proxy routes /api/v1/* to this app, set root_path to "/api/v1"
    root_path=settings.context_path,
)

# Store settings in app state for access in route handlers
app.state.settings = settings


@app.get("/hi")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": f"Hello from {settings.app_name}"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }
