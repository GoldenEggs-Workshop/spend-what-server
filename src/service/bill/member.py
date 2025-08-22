from uuid import uuid4
from datetime import datetime
from typing import Annotated, Sequence

from beanie import PydanticObjectId, Link
from fastapi import HTTPException, APIRouter, Body
from pydantic import BaseModel, Field, create_model

from src.db import Bill, BillAccessRole, BillAccess, BillItem, mongo_transaction, BillMember, User, BillShareToken, \
    run_transaction_with_retry
from .bill import check_bill_permission
from ..models import BillPublic
from ..user import UserSessionParsed

router = APIRouter(prefix="/member", tags=['bill/member'])


class AddBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    name: Annotated[str, Field(title="成员名称", min_length=1, max_length=64)]
    user_id: Annotated[PydanticObjectId | None, Field(title="用户ID")] = None


@router.post("/add")
async def add_bill_member(user: UserSessionParsed, params: AddBillMemberParams) -> BillMember:
    """添加一个账单成员"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")

    async def _txn(session):
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                                           session=session)
        bill_member = await BillMember(name=params.name, linked_user=params.user_id).insert(session=session)
        bill.members.append(BillMember.link_from_id(bill_member.id))
        await bill.save(session=session)
        return bill_member

    return await run_transaction_with_retry(_txn)


class RemoveBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    bill_member_id: Annotated[PydanticObjectId, Field(title="成员ID")]


@router.post("/remove")
async def remove_bill_member(user: UserSessionParsed, params: RemoveBillMemberParams) -> str:
    """移除一个账单成员"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                                           session=session)

        bill_member = await BillMember.get(params.bill_member_id, session=session)

        if bill_member is None:
            raise HTTPException(status_code=404, detail="Bill member not found.")

        if bill_member.id not in [m.ref.id for m in bill.members]:
            raise HTTPException(status_code=400, detail="Member not found in the bill.")

        bill.members = [m for m in bill.members if m.ref.id != bill_member.id]

        await bill.save(session=session)
        await bill_member.delete(session=session)
    return "ok"


class BindBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    bill_member_id: Annotated[PydanticObjectId, Field(title="账单成员ID")]
    user_id: Annotated[PydanticObjectId | None, Field(title="用户ID")]


@router.post("/bind")
async def bind_bill_member(user: UserSessionParsed, params: BindBillMemberParams) -> str:
    """绑定账单成员到用户"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                                           session=session)
        bill_member = await BillMember.get(params.bill_member_id, session=session)
        if bill_member is None or bill_member.id not in [m.ref.id for m in bill.members]:
            raise HTTPException(status_code=404, detail="Bill member not found.")
        bill_member.linked_user = await User.get(params.user_id, session=session) if params.user_id else None
        await bill_member.save(session=session)
    return "ok"


class UpdateBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    bill_member_id: Annotated[PydanticObjectId, Field(title="成员ID")]
    name: Annotated[str, Field(title="成员名称", min_length=1, max_length=64)]


@router.post("/update")
async def update_bill_member(user: UserSessionParsed, params: UpdateBillMemberParams) -> str:
    """更新账单成员信息"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(
            params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
            session=session
        )
        bill_member = await BillMember.get(params.bill_member_id, session=session)
        if bill_member is None or bill_member.id not in [m.ref.id for m in bill.members]:
            raise HTTPException(status_code=404, detail="Bill member not found.")
        await bill_member.set({"name": params.name}, session=session)
    return "ok"
