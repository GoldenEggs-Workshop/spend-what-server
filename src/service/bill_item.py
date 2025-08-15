from datetime import datetime
from typing import Annotated, Sequence

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from src.db import Bill, BillItem, BillAccess, BillAccessRole, mongo_transaction
from .user import UserSessionParsed
from src.types import PydanticDecimal128
from .bill import check_bill_permission

router = APIRouter(prefix="/bill/item", tags=['bill/item'])


async def get_bill_item_with_permission(
    bill_id: PydanticObjectId,
    item_id: PydanticObjectId,
    user: UserSessionParsed,
    allowed_roles: Sequence[BillAccessRole],
    session=None
) -> BillItem:
    # 校验账单权限
    await check_bill_permission(bill_id, user, allowed_roles, session=session)

    # 查找条目
    item = await BillItem.find_one({"_id": item_id, "bill.$id": bill_id}, session=session)
    if item is None:
        raise HTTPException(status_code=404, detail="Bill item not found.")

    return item


class CreateBillItemParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单 ID")]
    type: Annotated[str, Field(title="类型", max_length=64)]
    type_icon: Annotated[str, Field(title="类型图标")]
    description: Annotated[str, Field(title="描述", max_length=256)]
    amount: Annotated[PydanticDecimal128, Field(title="金额")]
    currency: Annotated[str, Field(title="货币")]
    paid_by: Annotated[str, Field(title="付款人", max_length=64)]
    occurred_time: Annotated[datetime, Field(title="发生时间")]


@router.post("/create")
async def create_bill_item(user: UserSessionParsed, params: CreateBillItemParams) -> dict:
    """创建账单条目"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(
            params.bill_id,
            user,
            [BillAccessRole.OWNER, BillAccessRole.MEMBER],
            session=session
        )

        if params.paid_by not in bill.members:
            raise HTTPException(status_code=400, detail="Paid by user is not a member of the bill.")

        now = datetime.now()
        item = BillItem(
            bill=bill.to_ref(),
            type=params.type,
            type_icon=params.type_icon,
            description=params.description,
            amount=params.amount,
            currency=params.currency,
            created_by=user.to_ref(),
            paid_by=params.paid_by,
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
    async with mongo_transaction() as session:
        item = await get_bill_item_with_permission(
            params.bill_id, params.item_id, user,
            [BillAccessRole.OWNER, BillAccessRole.MEMBER],
            session=session
        )
        await item.delete(session=session)

    return "ok"


class ListBillItemParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID", embed=True)]
    skip: Annotated[int, Field(title="跳过的账单条目数量", ge=0)] = 0
    limit: Annotated[int, Field(title="账单条目数量", ge=0, le=128)] = 16


@router.post("/list")
async def list_bill_items(user: UserSessionParsed, params: ListBillItemParams) -> list[BillItem]:
    """列出账单条目"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    await check_bill_permission(
        params.bill_id,
        user,
        [BillAccessRole.OWNER, BillAccessRole.MEMBER, BillAccessRole.OBSERVER]
    )

    pipeline = [
        # 1. 匹配当前账单的 BillItem 记录
        {"$match": {"bill.$id": params.bill_id}},

        # 2. 按 bill_doc.item_updated_time 降序排序
        {"$sort": {"occurred_time": -1}},

        # 3. 跳过 skip 条，限制 limit 条
        {"$skip": params.skip},
        {"$limit": params.limit},
    ]
    bills = await BillItem.aggregate(pipeline).to_list()
    return bills


class UpdateBillItemParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单 ID")]
    item_id: Annotated[PydanticObjectId, Field(title="条目 ID")]
    type: Annotated[str, Field(title="类型", max_length=64)]
    type_icon: Annotated[str, Field(title="类型图标")]
    description: Annotated[str, Field(title="描述", max_length=256)]
    amount: Annotated[PydanticDecimal128, Field(title="金额")]
    currency: Annotated[str, Field(title="货币")]
    paid_by: Annotated[str, Field(title="付款人", max_length=64)]
    occurred_time: Annotated[datetime, Field(title="发生时间")]


@router.post("/update")
async def update_bill_item(user: UserSessionParsed, params: UpdateBillItemParams):
    """更新账单条目"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        item = await get_bill_item_with_permission(
            params.bill_id, params.item_id, user,
            [BillAccessRole.OWNER, BillAccessRole.MEMBER],
            session=session
        )

        bill = await item.bill.fetch()

        if params.paid_by not in bill.members:
            raise HTTPException(status_code=400, detail="Paid by user is not a member of the bill.")

        await item.update(
            {
                "$set": {
                    "type": params.type,
                    "type_icon": params.type_icon,
                    "description": params.description,
                    "amount": params.amount,
                    "currency": params.currency,
                    "occurred_time": params.occurred_time
                }
            },
            session=session
        )

        return "ok"
