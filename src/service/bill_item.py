from datetime import datetime
from decimal import Decimal
from typing import Annotated, Sequence

from beanie import PydanticObjectId, Indexed
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from pymongo import DESCENDING

from src.db import client, Bill, BillItem, BillAccess, BillAccessRole, BillLog
from src.service.user import UserSessionParsed

router = APIRouter(prefix="/bill/item", tags=['bill/item'])


async def check_bill_permission(
    bill_id: PydanticObjectId,
    user: UserSessionParsed,
    allowed_roles: Sequence[BillAccessRole],
    session=None
) -> Bill:
    """检查用户是否有访问账单的权限，返回 Bill 对象"""
    bill = await Bill.get(bill_id, session=session)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")

    has_access = await BillAccess.find_one({
        "bill.$id": bill.id,
        "user.$id": user.id,
        "role": {"$in": allowed_roles}
    }, session=session)
    if has_access is None:
        raise HTTPException(status_code=403, detail="You do not have permission for this bill.")
    return bill


class CreateBillItemParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单 ID")]
    type: Annotated[str, Field(title="类型", max_length=64)]
    type_icon: Annotated[str, Field(title="类型图标")]
    description: Annotated[str, Field(title="描述", max_length=256)]
    amount: Annotated[Decimal, Field(title="金额")]
    currency: Annotated[str, Field(title="货币")]
    occurred_time: Annotated[datetime, Field(title="发生时间")]


@router.post("/create")
async def create_bill_item(user: UserSessionParsed, params: CreateBillItemParams) -> dict:
    """创建账单条目"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with client.start_session() as session:
        async with await session.start_transaction():
            bill = await check_bill_permission(
                params.bill_id,
                user,
                [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                session=session
            )

            now = datetime.now()
            item = BillItem(
                bill=bill.to_ref(),
                type=params.type,
                type_icon=params.type_icon,
                description=params.description,
                amount=params.amount,
                currency=params.currency,
                created_time=now,
                occurred_time=params.occurred_time
            )
            await item.insert(session=session)
    return {"item_id": str(item.id)}


class DeleteBillItemParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    item_id: Annotated[PydanticObjectId, Field(title="条目ID")]


@router.post("/delete")
async def delete_bill_item(user: UserSessionParsed, params: DeleteBillItemParams):
    """删除账单条目"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with client.start_session() as session:
        async with await session.start_transaction():
            await check_bill_permission(
                params.bill_id,
                user,
                [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                session=session
            )

            item = await BillItem.find_one({"_id": params.item_id, "bill.$id": params.bill_id}, session=session)
            if item is None:
                raise HTTPException(status_code=404, detail="Bill item not found.")
            await item.delete(session=session)

    return "ok"
