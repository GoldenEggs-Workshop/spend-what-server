from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from beanie import Document, Indexed, Link
from pydantic import Field


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


class Bill(Document):
    """账单"""
    title: Annotated[str, Field(title="标题")]
    created_time: datetime
    item_updated_time: datetime

    class Settings:
        name = "bill"


class BillMemberRole(Enum):
    """账单成员角色"""
    OWNER = "owner"
    MEMBER = "member"
    OBSERVER = "observer"


class BillMember(Document):
    """账单成员"""
    bill: Annotated[Link[Bill], Indexed()]
    user: Annotated[Link[User], Indexed()]
    role: Annotated[BillMemberRole, Field(title="角色")] = BillMemberRole.OBSERVER

    class Settings:
        name = "bill_member"


class BillItem(Document):
    """账单条目"""
    bill: Annotated[Link[Bill], Indexed()]
    description: Annotated[str, Field(title="描述")]
    amount: Annotated[Decimal, Field(title="金额")]
    currency: Annotated[str, Field(title="货币")] = "CNY"
    created_time: datetime

    class Settings:
        name = "bill_item"
