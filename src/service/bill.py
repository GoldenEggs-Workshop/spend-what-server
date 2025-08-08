from datetime import datetime
from typing import cast

from fastapi import HTTPException, APIRouter, Body

from src.db import Bill, BillMemberRole, BillMember
from .user import UserSessionParsed

router = APIRouter(prefix="/bill", tags=['bill'])


@router.post("/list")
async def list_bills(user: UserSessionParsed) -> list[Bill]:
    """获取用户的账单列表"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    bill_members = await BillMember.find(BillMember.user.id == user.id, fetch_links=True).to_list()
    # bills = [await Bill.get(bill_member.bill.ref.id) for bill_member in bill_members]

    bills = cast(list[Bill], [bm.bill for bm in bill_members])
    return bills


@router.post("/create")
async def create_bill(user: UserSessionParsed, title: str = Body(title="账单标题", embed=True)):
    """创建一个新的账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    bill = Bill(title=title, created_time=datetime.now(), item_updated_time=datetime.now())
    await bill.insert()
    await BillMember(bill=bill, user=user, role=BillMemberRole.OWNER).insert()
    # Optionally, you can add the user as a member of the bill
    # await BillMember(bill=bill, user=user, role=BillMemberRole.OWNER).insert()

    return {"bill_id": str(bill.id)}
