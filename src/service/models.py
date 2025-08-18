from datetime import datetime
from typing import Annotated

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from src.db import BillMember, Bill


class UserPublic(BaseModel):
    """公开用户信息"""
    id: PydanticObjectId
    username: Annotated[str, Field(title="用户名")]


class BillMemberPublic(BaseModel):
    """公开账单成员信息"""
    id: PydanticObjectId
    name: Annotated[str, Field(title="成员名称", min_length=1, max_length=64)]
    linked_user: Annotated[UserPublic | None, Field(title="关联用户")] = None

    @classmethod
    async def from_orm_bill_member(cls, bill_member):
        # 先展开 link
        if bill_member.linked_user is not None:
            await bill_member.fetch_link(BillMember.linked_user)
            linked_user = UserPublic(
                id=str(bill_member.linked_user.id),
                username=bill_member.linked_user.username,
                email=getattr(bill_member.linked_user, "email", None)
            )
        else:
            linked_user = None
        return cls(
            id=str(bill_member.id),
            name=bill_member.name,
            linked_user=linked_user
        )


class BillPublic(BaseModel):
    """公开账单信息"""
    id: PydanticObjectId
    title: Annotated[str, Field(title="标题")]
    members: Annotated[list[BillMemberPublic], Field(title="成员列表")]
    created_by: Annotated[UserPublic, Field(title="创建人")]
    created_time: Annotated[datetime, Field(title="创建时间")]
    item_updated_time: Annotated[datetime, Field(title="更新时间")]
    occurred_at: Annotated[datetime, Field(title="发生时间")]
    currency: Annotated[str, Field(title="货币")]

    @classmethod
    async def from_orm_bill(cls, bill):
        # 先展开 link
        await bill.fetch_link(Bill.created_by)
        await bill.fetch_link(Bill.members)
        return cls(
            id=str(bill.id),
            title=bill.title,
            members=[await BillMemberPublic.from_orm_bill_member(m) for m in bill.members],
            created_by=UserPublic(
                id=str(bill.created_by.id),
                username=bill.created_by.username,
                email=getattr(bill.created_by, "email", None)
            ),
            created_time=bill.created_time,
            item_updated_time=bill.item_updated_time,
            occurred_at=bill.occurred_at,
            currency=bill.currency,
        )

