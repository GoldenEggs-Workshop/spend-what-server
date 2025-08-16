from fastapi import APIRouter
from .user import router as user_router
from .bill import router as bill_router

router = APIRouter(prefix="/api")

router.include_router(user_router)
router.include_router(bill_router)
