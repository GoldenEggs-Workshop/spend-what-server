import asyncio
from contextlib import asynccontextmanager

from pymongo import AsyncMongoClient
from pymongo.errors import OperationFailure

client = AsyncMongoClient("mongodb://127.0.0.1:27017/spend_what")


@asynccontextmanager
async def mongo_transaction():
    async with client.start_session() as session:
        async with await session.start_transaction():
            yield session


async def run_transaction_with_retry(fn, retries: int = 3, backoff: float = 0.1):
    """
    封装事务重试逻辑
    - fn: 事务函数，接收 session 参数
    - retries: 最大重试次数
    - backoff: 初始退避时间（秒），每次冲突翻倍
    """
    for attempt in range(retries):
        try:
            async with mongo_transaction() as session:
                return await fn(session)
        except OperationFailure as e:
            if "TransientTransactionError" in e.details.get("errorLabels", []) and attempt < retries - 1:
                # 指数退避
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            raise
