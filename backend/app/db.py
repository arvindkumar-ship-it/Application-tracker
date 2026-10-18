from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True, connect_args={"timeout": 3, "server_settings": {"timezone": "UTC"}})
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with session_factory() as session:
        yield session
