from beanie import init_beanie

from src.db.client import client
from src.db.models import *


async def init_client():
    await init_beanie(
        database=client.get_database(),
        document_models=[
            User, UserSession,
            Bill, BillMember, BillItem
        ]
    )
