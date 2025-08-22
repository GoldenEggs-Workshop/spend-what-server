from uuid import uuid4
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from beanie import PydanticObjectId, Link
from fastapi import HTTPException, APIRouter, Body
from pydantic import BaseModel, Field, create_model

from src.db import Bill, BillAccessRole, BillAccess, BillItem, mongo_transaction, BillMember, User, BillShareToken
from .bill import check_bill_permission
from ..models import BillPublic
from ..user import UserSessionParsed

router = APIRouter(prefix="/share", tags=['bill/share'])


class ShareBillParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    access_role: Annotated[BillAccessRole, Field(title="访问权限角色")] = BillAccessRole.OBSERVER
    expires_at: Annotated[datetime | None, Field(title="过期时间")] = None
    remaining_uses: Annotated[int | None, Field(title="剩余使用次数")] = None
    bill_member_id: Annotated[PydanticObjectId | None, Field(title="账单成员ID")] = None


@router.post("/", response_model=create_model(
    "ShareBillResponse",
    token=(str, Field(title="分享令牌"))
))
async def share_bill(user: UserSessionParsed, params: ShareBillParams) -> dict:
    """分享账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER], session=session)
        if params.bill_member_id is not None:
            bill_member = await BillMember.get(params.bill_member_id, session=session)
            if bill_member.id not in [m.ref.id for m in bill.members]:
                raise HTTPException(status_code=404, detail="Bill member not found.")
        else:
            bill_member = None

        now = datetime.now(ZoneInfo("UTC"))
        bill_share_token = BillShareToken(
            token=str(uuid4()),
            bill=bill,
            access_role=params.access_role,
            created_by=user,
            created_time=now,
            expires_at=params.expires_at,
            remaining_uses=params.remaining_uses,
            bill_member=bill_member,
        )
        await bill_share_token.insert(session=session)
    return {"token": bill_share_token.token}


@router.post("/delete_all")
async def delete_all_share_tokens(user: UserSessionParsed,
                                  bill_id: PydanticObjectId = Body(title="账单ID", embed=True)) -> str:
    """删除某个账单的所有分享令牌"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(bill_id, user, [BillAccessRole.OWNER], session=session)
        await BillShareToken.find({"bill.$id": bill.id}, session=session).delete(session=session)
    return "ok"


@router.post("/consume", response_model=create_model(
    "ConsumeShareBillTokenResponse",
    bill_id=(PydanticObjectId, Field(title="账单ID"))
))
async def consume_share_bill_token(user: UserSessionParsed, token: str = Body(title="Token", embed=True)) -> dict:
    """使用分享令牌加入账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        share_token = await BillShareToken.find_one(BillShareToken.token == token, session=session)
        if share_token is None:
            raise HTTPException(status_code=404, detail="Share token not found.")
        now = datetime.now(ZoneInfo("UTC"))
        if share_token.expires_at and share_token.expires_at < now:
            raise HTTPException(status_code=400, detail="Share token has expired.")
        if share_token.remaining_uses is not None and share_token.remaining_uses <= 0:
            raise HTTPException(status_code=400, detail="Share token has no remaining uses.")

        # 检查用户是否已经有访问权限
        existing_access = await BillAccess.find_one(
            {"bill.$id": share_token.bill.ref.id, "user.$id": user.id},
            session=session
        )
        if existing_access is not None:
            raise HTTPException(status_code=400, detail="You already have access to this bill.")

        await BillAccess(bill=share_token.bill, user=user, role=share_token.access_role).insert(session=session)

        if share_token.bill_member:
            # 如果分享令牌关联了账单成员，则将用户绑定到该成员
            bill_member = await BillMember.get(share_token.bill_member.ref.id, session=session)
            bill_member.linked_user = User.link_from_id(user.id)
            await bill_member.save(session=session)

        if share_token.remaining_uses is not None:
            share_token.remaining_uses -= 1
            await share_token.save(session=session)

        return {"bill_id": share_token.bill.ref.id}


class PublicBillShareToken(BaseModel):
    token: str = Field(title="分享令牌")
    access_role: BillAccessRole = Field(title="访问角色")
    created_by: str = Field(title="创建人用户名")
    created_time: datetime = Field(title="创建时间")
    expires_at: datetime | None = Field(title="过期时间", default=None)
    remaining_uses: int | None = Field(title="剩余使用次数", default=None)
    bill_member_name: str | None = Field(title="关联账单成员名称", default=None)

    @classmethod
    async def from_share_token(cls, token: BillShareToken) -> "PublicBillShareToken":
        await token.fetch_link(BillShareToken.created_by)
        if token.bill_member is not None:
            await token.fetch_link(BillShareToken.bill_member)
            assert isinstance(token.bill_member, BillMember)
        assert isinstance(token.created_by, User)

        return cls(
            token=token.token,
            access_role=token.access_role,
            created_by=token.created_by.username,
            created_time=token.created_time,
            expires_at=token.expires_at,
            remaining_uses=token.remaining_uses,
            bill_member_name=str(token.bill_member.name) if token.bill_member else None
        )


@router.post("/list")
async def list_share_tokens(
    user: UserSessionParsed,
    bill_id: PydanticObjectId = Body(title="账单ID", embed=True),
) -> list[PublicBillShareToken]:
    """列出某个账单的所有分享令牌"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        await check_bill_permission(bill_id, user, [BillAccessRole.OWNER], session=session)
        tokens = await BillShareToken.find({"bill.$id": bill_id}, session=session).to_list()
    return [await PublicBillShareToken.from_share_token(token) for token in tokens]


@router.post("delete")
async def delete_share_token(
    user: UserSessionParsed,
    token: str = Body(title="Token", embed=True),
    bill_id: PydanticObjectId = Body(title="账单ID", embed=True),
) -> str:
    """删除分享令牌"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        await check_bill_permission(bill_id, user, [BillAccessRole.OWNER],
                                    session=session)

        share_token = await BillShareToken.find_one({"token": token, "bill.$id": bill_id}, session=session)

        if share_token is None:
            raise HTTPException(status_code=404, detail="Share token not found.")
        await share_token.delete(session=session)
    return "ok"
