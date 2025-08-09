from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.db import init_client, client
from src.service import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_client()
    yield
    await client.close()


app = FastAPI(lifespan=lifespan)
app.include_router(router)


def main():
    uvicorn.run("main:app", host="0.0.0.0", port=8000)


if __name__ == '__main__':
    main()
