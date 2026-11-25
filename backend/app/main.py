from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.config import settings
from app.database import get_db
from app.services.scheduler.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous company intelligence and executive briefing engine.",
    lifespan=lifespan,
)

# Register API v1 routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
def read_root():
    """Returns basic project metadata."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Checks API and database health using SQLAlchemy 'SELECT 1'.
    Returns health status without exposing sensitive credentials or host details.
    """
    health_report = {
        "status": "healthy",
        "api": "online",
        "database": "connected",
    }
    try:
        result = db.execute(text("SELECT 1")).scalar()
        if result != 1:
            raise RuntimeError("Database query returned an unexpected response.")
    except Exception:
        health_report["status"] = "degraded"
        health_report["database"] = "disconnected"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health_report,
        )

    return health_report
