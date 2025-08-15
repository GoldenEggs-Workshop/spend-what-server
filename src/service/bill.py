from uuid import uuid4
from datetime import datetime
from typing import Annotated, Sequence

from beanie import PydanticObjectId, Link
from fastapi import HTTPException, APIRouter, Body
from pydantic import BaseModel, Field, create_model

from src.db import Bill, BillAccessRole, BillAccess, BillItem, mongo_transaction, BillMember, User, BillShareToken
from .user import UserSessionParsed

router = APIRouter(prefix="/bill", tags=['bill'])
member_router = APIRouter(prefix="/bill/member", tags=['bill/member'])
share_router = APIRouter(prefix="/bill/share", tags=['bill/share'])


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
async def list_bills(user: UserSessionParsed, params: ListBillParams) -> list[Bill]:
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
    # print(type(bills), bills)
    return bills


@router.post("/create")
async def create_bill(user: UserSessionParsed, title: str = Body(title="账单标题", embed=True)) -> Bill:
    """创建一个新的账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = Bill(title=title, members=[], created_by=user,
                    created_time=datetime.now(),
                    item_updated_time=datetime.now())
        await bill.insert(session=session)
        await BillAccess(bill=bill.to_ref(), user=user, role=BillAccessRole.OWNER).insert(session=session)
    return bill


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


class Access(BaseModel):
    user_id: Annotated[PydanticObjectId, Field(title="用户ID")]
    role: Annotated[BillAccessRole, Field(title="访问权限角色")]


class UpdateBillAccessParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    access_list: Annotated[list[Access], Field(title="访问权限列表", max_length=128)]


@router.post("/access/update")
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


# class UpdateBillMembersParams(BaseModel):
#     id: Annotated[PydanticObjectId, Field(title="账单ID")]
#     members: Annotated[list[str], Field(title="成员名称列表", max_length=128)]


# @router.post("/member/update")
# async def update_bill_members(user: UserSessionParsed, params: UpdateBillMembersParams):
#     """更新账单成员列表"""
#     if user is None:
#         raise HTTPException(status_code=401, detail="User not authenticated.")
#     async with mongo_transaction() as session:
#         bill = await check_bill_permission(params.id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
#                                            session=session)
#         bill.members = params.members
#         await bill.save(session=session)
#     return "ok"


class AddBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    name: Annotated[str, Field(title="成员名称", min_length=1, max_length=64)]


@member_router.post("/add")
async def add_bill_member(user: UserSessionParsed, params: AddBillMemberParams) -> BillMember:
    """添加一个账单成员"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                                           session=session)
        bill_member = await BillMember(name=params.name).insert(session=session)
        bill.members.append(bill_member)
        await bill.save(session=session)
    return bill_member


class RemoveBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    bill_member_id: Annotated[PydanticObjectId, Field(title="成员ID")]


@member_router.post("/remove")
async def remove_bill_member(user: UserSessionParsed, params: RemoveBillMemberParams) -> str:
    """移除一个账单成员"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                                           session=session)

        bill_member = await BillMember.get(params.bill_member_id, session=session)

        if bill_member not in bill.members:
            raise HTTPException(status_code=400, detail="Member not found in the bill.")
        bill.members.remove(bill_member)
        await bill.save(session=session)
        await bill_member.delete(session=session)
    return "ok"


class BindBillMemberParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    bill_member_id: Annotated[PydanticObjectId, Field(title="账单成员ID")]
    user_id: Annotated[PydanticObjectId | None, Field(title="用户ID")]


@member_router.post("/bind")
async def bind_bill_member(user: UserSessionParsed, params: BindBillMemberParams) -> str:
    """绑定账单成员到用户"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER, BillAccessRole.MEMBER],
                                           session=session)
        bill_member = await BillMember.get(params.bill_member_id, session=session)
        if bill_member is None or bill_member not in bill.members:
            raise HTTPException(status_code=404, detail="Bill member not found.")
        bill_member.linked_user = User.get(params.user_id, session=session) if params.user_id else None
        await bill_member.save(session=session)
    return "ok"


class ShareBillParams(BaseModel):
    bill_id: Annotated[PydanticObjectId, Field(title="账单ID")]
    access_role: Annotated[BillAccessRole, Field(title="访问权限角色")] = BillAccessRole.OBSERVER
    expires_at: Annotated[datetime | None, Field(title="过期时间")] = None
    remaining_uses: Annotated[int | None, Field(title="剩余使用次数")] = None
    bill_member_id: Annotated[PydanticObjectId | None, Field(title="账单成员ID")] = None


@share_router.post("/", response_model=create_model(
    "ShareBillResponse",
    token=(str, Field(title="分享令牌"))
))
async def share_bill(user: UserSessionParsed, params: ShareBillParams) -> dict:
    """分享账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        bill = await check_bill_permission(params.bill_id, user, [BillAccessRole.OWNER], session=session)

        bill_member = await BillMember.get(params.bill_member_id, session=session)
        if bill_member is None or bill_member not in bill.members:
            raise HTTPException(status_code=404, detail="Bill member not found.")

        now = datetime.now()
        bill_share_token = BillShareToken(
            token=str(uuid4()),
            bill=bill,
            access_role=params.access_role,
            created_by=user,
            crated_time=now,
            expires_at=params.exprires_at,
            remaining_uses=params.remaining_uses,
            bill_member=bill_member,
        )
        await bill_share_token.insert(session=session)
    return {"token": bill_share_token.token}


@share_router.post("/consume")
async def consume_share_bill_token(user: UserSessionParsed, token: str = Body(title="Token", embed=True)) -> str:
    """使用分享令牌加入账单"""
    if user is None:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    async with mongo_transaction() as session:
        share_token = await BillShareToken.find_one(BillShareToken.token == token, session=session)
        if share_token is None:
            raise HTTPException(status_code=404, detail="Share token not found.")
        now = datetime.now()
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
            bill_member.linked_user = user
            await bill_member.save(session=session)

        if share_token.remaining_uses is not None:
            share_token.remaining_uses -= 1
            await share_token.save(session=session)

        return "ok"
