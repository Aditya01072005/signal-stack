from fastapi import APIRouter
from app.api.v1.briefs import router as briefs_router
from app.api.v1.companies import router as companies_router
from app.api.v1.competitors import router as competitors_router
from app.api.v1.documents import router as documents_router
from app.api.v1.interview import router as interview_router
from app.api.v1.monitoring import router as monitoring_router
from app.api.v1.research import router as research_router
from app.api.v1.signal_analysis import router as signal_analysis_router
from app.api.v1.scheduler import router as scheduler_router
from app.api.v1.sources import router as sources_router

api_router = APIRouter()
api_router.include_router(companies_router)
api_router.include_router(competitors_router)
api_router.include_router(documents_router)
api_router.include_router(research_router)
api_router.include_router(sources_router)
api_router.include_router(interview_router)
api_router.include_router(monitoring_router)
api_router.include_router(signal_analysis_router)
api_router.include_router(briefs_router)
api_router.include_router(scheduler_router)
