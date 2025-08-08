from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

from fastapi import HTTPException, APIRouter, Response, Cookie, Depends
from pydantic import Field, BaseModel
from pymongo.errors import DuplicateKeyError

from src.db import User, UserSession

router = APIRouter(prefix="/user", tags=['user'])


async def parse_user_session(session: str = Cookie(None)) -> User | None:
    if session is None:
        return None
    user_session = await UserSession.find_one(UserSession.value == session)
    if user_session is None:
        return None
    if user_session.expires_at < datetime.now():
        await user_session.delete()
        return None
    now = datetime.now()
    if user_session.expires_at - now < timedelta(days=1):
        user_session.expires_at = datetime.now() + timedelta(days=30)
        await user_session.save()
    return await User.get(user_session.user.ref.id)


UserSessionParsed = Annotated[User, Depends(parse_user_session)]


class ApiUser(BaseModel):
    username: Annotated[str, Field(min_length=3)]
    password: str


@router.post("/register")
async def register_user(user: Annotated[ApiUser, Field(title="用户")]):
    password = sha256(user.password.encode("utf-8")).hexdigest()
    user = User(username=user.username, password_sha256=password)
    try:
        await user.insert()
    except DuplicateKeyError as e:
        k = e.details['keyValue'].keys()
        k = list(k)[0]
        raise HTTPException(status_code=400, detail=f"{k} is already existed.")
    return ""


@router.post("/login")
async def login_user(params: ApiUser, resp: Response):
    user = await User.find_one(User.username == params.username)
    if user is None:
        raise HTTPException(status_code=400, detail="Username or password are not matched.")
    password_sha256 = sha256(params.password.encode("utf-8")).hexdigest()
    if password_sha256 != user.password_sha256:
        raise HTTPException(status_code=400, detail="Username or password are not matched.")
    session = str(uuid4())
    now = datetime.now()
    await UserSession(value=session, expires_at=now + timedelta(days=30), user=user).insert()
    resp.set_cookie("session", session)
    return ""
