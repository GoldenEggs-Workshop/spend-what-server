from datetime import datetime
from decimal import Decimal
from typing import Annotated

from beanie import PydanticObjectId, Indexed
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo import DESCENDING

from src.db import client, Bill, BillItem, BillAccess, BillAccessRole, BillLog
from src.service.user import UserSessionParsed

router = APIRouter(prefix="/bill/item", tags=['bill/item'])


class CreateBillItemParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单 ID")]
    type: Annotated[str, Field(title="类型", max_length=64)]
    type_icon: Annotated[str, Field(title="类型图标")]
    description: Annotated[str, Field(title="描述", max_length=256)]
    amount: Annotated[Decimal, Field(title="金额")]
    currency: Annotated[str, Field(title="货币")]
    occurred_time: Annotated[datetime, Field(title="发生时间")]


@router.post("/create")
async def create_bill_item(user: UserSessionParsed, params: CreateBillItemParams):
    """创建账单条目"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with client.start_session() as session:
        async with await session.start_transaction():
            bill = await Bill.get(params.bill_id, session=session)
            if bill is None:
                raise HTTPException(status_code=404, detail="Bill not found.")
            if await BillAccess.find_one({
                "bill.$id": bill.id,
                "user.$id": user.id,
                "role": {"$in": [BillAccessRole.OWNER, BillAccessRole.MEMBER]}
            }, session=session) is None:
                raise HTTPException(status_code=403, detail="You do not have permission to add items to this bill.")

            now = datetime.now()
            item = BillItem(
                bill=bill.to_ref(),
                type=params.type,
                type_icon=params.type_icon,
                description=params.description,
                amount=params.amount,
                currency=params.currency,
                create_time=now,
                occurred_time=params.occurred_time
            )
            await item.insert(session=session)
    return "ok"
