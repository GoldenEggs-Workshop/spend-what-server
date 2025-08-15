from datetime import datetime
from enum import Enum
from typing import Annotated

from beanie import Document, Indexed, Link
# from bson import Decimal128
from pydantic import Field
from pymongo import DESCENDING

from src.types import PydanticDecimal128


class User(Document):
    """用户"""
    username: Annotated[str, Field(title="用户名"), Indexed(unique=True)]
    password_sha256: Annotated[str, Field(title="密码")]
    role: Annotated[str, Field(title="角色")] = "user"

    class Settings:
        name = "user"


class UserSession(Document):
    """用户会话"""
    value: Annotated[str, Indexed(unique=True)]
    expires_at: datetime
    user: Link[User]

    class Settings:
        name = "user_session"


class BillMember(Document):
    """账单成员"""
    name: Annotated[str, Field(title="成员名称", min_length=1, max_length=64), Indexed()]
    linked_user: Annotated[Link[User] | None, Field(title="关联用户"), Indexed()] = None

    class Settings:
        name = "bill_member"


class Bill(Document):
    """账单"""
    title: Annotated[str, Field(title="标题")]
    members: Annotated[list[BillMember], Field(title="成员列表")] = []
    created_by: Annotated[Link[User], Field(title="创建人"), Indexed()]
    created_time: Annotated[datetime, Field(title="创建时间"), Indexed(index_type=DESCENDING)]
    item_updated_time: Annotated[datetime, Field(title="更新时间"), Indexed(index_type=DESCENDING)]

    class Settings:
        name = "bill"


class BillAccessRole(Enum):
    """账单成员角色"""
    OWNER = "owner"
    MEMBER = "member"
    OBSERVER = "observer"


class BillAccess(Document):
    """账单访问权限"""
    bill: Annotated[Link[Bill], Indexed()]
    user: Annotated[Link[User], Indexed()]
    role: Annotated[BillAccessRole, Field(title="权限角色")] = BillAccessRole.OBSERVER

    class Settings:
        name = "bill_access"


class BillItem(Document):
    """账单条目"""

    bill: Annotated[Link[Bill], Indexed()]
    type: Annotated[str, Field(title="类型", max_length=64)]
    type_icon: Annotated[str, Field(title="类型图标")] = "🧐"
    description: Annotated[str, Field(title="描述", max_length=256)]
    amount: Annotated[PydanticDecimal128, Field(title="金额")]
    currency: Annotated[str, Field(title="货币")]
    created_by: Annotated[Link[User], Field(title="创建人"), Indexed()]
    paid_by: Annotated[Link[BillMember], Field(title="付款人"), Indexed()]
    created_time: Annotated[datetime, Field(title="创建时间")]
    occurred_time: Annotated[datetime, Field(title="发生时间"), Indexed(index_type=DESCENDING)]

    class Settings:
        name = "bill_item"


class BillAction(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class BillLog(Document):
    """账单日志"""
    bill: Annotated[Link[Bill], Indexed()]
    user: Annotated[Link[User], Indexed()]
    action: Annotated[str, Field(title="操作")]
    description: Annotated[str, Field(title="描述")] = ""
    time: Annotated[datetime, Field(title="操作时间"), Indexed(index_type=DESCENDING)]

    class Settings:
        name = "bill_log"


class BillShareToken(Document):
    """账单分享令牌"""
    token: Annotated[str, Indexed(unique=True)]
    bill: Annotated[Link[Bill], Indexed()]
    access_role: Annotated[BillAccessRole, Field(title="访问角色")] = BillAccessRole.OBSERVER
    created_by: Annotated[Link[User], Indexed()]
    created_time: Annotated[datetime, Field(title="创建时间"), Indexed(index_type=DESCENDING)]

    class Settings:
        name = "bill_share_token"
