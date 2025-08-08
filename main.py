from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.db import init_client, client
from src.service.user import router as user_router
from src.service.bill import router as bill_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_client()
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)

app.include_router(user_router)
app.include_router(bill_router)


def main():
    uvicorn.run("main:app")


if __name__ == '__main__':
    main()
