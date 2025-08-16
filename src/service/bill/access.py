import asyncio
from uuid import uuid4
from datetime import datetime
from typing import Annotated

from beanie import PydanticObjectId, Link
from fastapi import HTTPException, APIRouter, Body
from pydantic import BaseModel, Field, create_model

from src.db import Bill, BillAccessRole, BillAccess, BillItem, mongo_transaction, BillMember, User, BillShareToken
from .bill import check_bill_permission
from ..models import BillPublic
from ..user import UserSessionParsed

router = APIRouter(prefix="/access", tags=['bill/access'])


class Access(BaseModel):
    user_id: Annotated[PydanticObjectId, Field(title="用户ID")]
    role: Annotated[BillAccessRole, Field(title="访问权限角色")]


class AccessPublic(Access):
    user_name: Annotated[str, Field(title="用户名")]


class UpdateBillAccessParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    access_list: Annotated[list[Access], Field(title="访问权限列表", max_length=128)]


@router.post("/update")
async def update_bill_access(user: UserSessionParsed, params: UpdateBillAccessParams) -> str:
    """更新账单访问权限"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER], session=session)
        await BillAccess.find(
            {"bill.$id": params.bill_id},
            session=session
        ).delete(session=session)
        # 添加新的访问权限
        for access in params.access_list:
            user_id = access.user_id
            role = access.role
            await BillAccess(bill=bill.to_ref(), user=user_id, role=role).insert(session=session)

    return "ok"


async def get_bill_access_list(bill_id: PydanticObjectId, session=None) -> list[AccessPublic]:
    """获取所有账单访问权限列表"""
    access_list = await BillAccess.find({"bill.$id": bill_id}, session=session).to_list()

    result = []
    for access in access_list:
        await access.fetch_link(BillAccess.user)
        assert isinstance(access.user, User)
        result.append(AccessPublic(user_id=access.user.id, role=access.role, user_name=access.user.username))
    return result


@router.post("/list")
async def list_bill_access(user: UserSessionParsed,
                           bill_id: PydanticObjectId = Body(title="账单ID", embed=True)) -> list[AccessPublic]:
    """获取账单的访问权限列表"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        await check_bill_permission(bill_id, user,
                                    [BillAccessRole.OWNER, BillAccessRole.MEMBER, BillAccessRole.OBSERVER],
                                    session=session)
        result = await get_bill_access_list(bill_id, session=session)
    return result
