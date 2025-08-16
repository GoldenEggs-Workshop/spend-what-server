from uuid import uuid4
from datetime import datetime
from typing import Annotated, Sequence

from beanie import PydanticObjectId, Link
from fastapi import HTTPException, APIRouter, Body
from pydantic import BaseModel, Field, create_model

from src.db import Bill, BillAccessRole, BillAccess, BillItem, mongo_transaction, BillMember, User, BillShareToken
from ..models import BillPublic
from ..user import UserSessionParsed

router = APIRouter(tags=['bill'])


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


class ListBillParams(BaseModel):
    skip: Annotated[int, Field(title="跳过的账单数量", ge=0)] = 0
    limit: Annotated[int, Field(title="账单数量", ge=0, le=128)] = 16


@router.post("/list")
async def list_bills(user: UserSessionParsed, params: ListBillParams) -> list[BillPublic]:
    """获取用户的账单列表"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    pipeline = [
        # 1. 匹配当前用户的 BillMember 记录
        {"$match": {"user.$id": user.id}},

        # 2. 通过 $lookup 关联 Bill 集合
        {
            "$lookup": {
                "from": "bill",  # 你数据库中 Bill 集合的名称，注意大小写
                "localField": "bill.$id",  # BillMember 的 bill 字段
                "foreignField": "_id",  # Bill 的 _id 字段
                "as": "bill_doc"
            }
        },

        # 3. 展开 bill_doc 数组，变成对象
        {"$unwind": "$bill_doc"},

        # 4. 按 bill_doc.item_updated_time 降序排序
        {"$sort": {"bill_doc.item_updated_time": -1}},

        # 5. 跳过 skip 条，限制 limit 条
        {"$skip": params.skip},
        {"$limit": params.limit},

        # 6. 最终只输出 bill_doc 部分（账单详细）
        {"$replaceRoot": {"newRoot": "$bill_doc"}},
    ]
    # bills_cursor = await db.bill_member.aggregate(pipeline)
    bills = await BillAccess.aggregate(pipeline).to_list()
    bills_public = []
    for b in bills:
        bill_public = await BillPublic.from_orm_bill(Bill.parse_obj(b))
        bills_public.append(bill_public)

    # print(type(bills), bills)
    return bills_public


@router.post("/create")
async def create_bill(user: UserSessionParsed, title: str = Body(title="账单标题", embed=True)) -> BillPublic:
    """创建一个新的账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = Bill(title=title, members=[], created_by=user,
                    created_time=datetime.now(),
                    item_updated_time=datetime.now())
        await bill.insert(session=session)
        await BillAccess(bill=bill.to_ref(), user=user, role=BillAccessRole.OWNER).insert(session=session)
    return await BillPublic.from_orm_bill(bill)


class DeleteBillsParams(BaseModel):
    id_list: Annotated[list[PydanticObjectId], Field(title="账单ID列表", max_length=128)]


@router.post("/multi/delete")
async def delete_bill(user: UserSessionParsed, params: DeleteBillsParams) -> str:
    """批量删除账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        async for member in BillAccess.find(
            {"bill.$id": {"$in": params.id_list}, "role": BillAccessRole.OWNER},
            session=session,
        ):
            if member.user.ref.id != user.id:
                raise HTTPException(status_code=403, detail="You do not have permission to delete these bills.")

        await BillAccess.find({"bill.$id": {"$in": params.id_list}}).delete(session=session)
        await Bill.find({"_id": {"$in": params.id_list}}).delete(session=session)
        await BillItem.find({"bill.$id": {"$in": params.id_list}}).delete(session=session)
    return "ok"


class UpdateBillParams(BaseModel):
    id: Annotated[PydanticObjectId, Field(title="账单ID")]
    title: Annotated[str, Field(title="账单标题", min_length=1)]


@router.post("/update")
async def update_bill(user: UserSessionParsed, params: UpdateBillParams) -> str:
    """更新账单信息"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await Bill.get(params.id, session=session)
        if bill is None:
            raise HTTPException(status_code=404, detail="Bill not found.")
        if await BillAccess.find_one(
            {"bill.$id": bill.id, "user.$id": user.id, "role": BillAccessRole.OWNER},
            session=session,
        ) is None:
            raise HTTPException(status_code=403, detail="You do not have permission to update this bill.")
        bill.title = params.title
        await bill.save(session=session)
    return "ok"



