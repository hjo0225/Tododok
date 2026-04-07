from fastapi import APIRouter

from .discussion import router as _discussion_router
from .scoring import router as _scoring_router
from .session import router as _session_router

router = APIRouter(prefix="/student", tags=["student"])
router.include_router(_session_router)
router.include_router(_discussion_router)
router.include_router(_scoring_router)
