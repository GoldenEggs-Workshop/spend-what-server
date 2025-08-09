from contextlib import asynccontextmanager

from pymongo import AsyncMongoClient

client = AsyncMongoClient("mongodb://127.0.0.1:27017/spend_what")


@asynccontextmanager
async def mongo_transaction():
    async with client.start_session() as session:
        async with await session.start_transaction():
            yield session
