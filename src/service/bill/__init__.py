from fastapi import APIRouter

from .bill import router as bill_router
from .member import router as bill_member_router
from .share import router as bill_share_router
from .item import router as bill_item_router
from .access import router as bill_access_router

router = APIRouter(prefix="/bill")
router.include_router(bill_router)
router.include_router(bill_member_router)
router.include_router(bill_share_router)
router.include_router(bill_item_router)
router.include_router(bill_access_router)
