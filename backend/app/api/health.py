import asyncio
from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text, select
from app.config import get_settings
from app.db import engine
from app.models.sync import app_setting
from app.tasks.celery_app import celery

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    result = {"db": False, "redis": False, "worker": False, "llm_key_present": bool(get_settings().anthropic_api_key), "sheet_configured": False}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            result["db"] = True
            values = dict((await connection.execute(select(app_setting.c.key, app_setting.c.value).where(app_setting.c.key.in_(["google_sheet_id", "google_sheet_tab_name"])))).all())
            result["sheet_configured"] = bool(values.get("google_sheet_id") and values.get("google_sheet_tab_name"))
    except Exception:
        pass
    try:
        async with Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2) as redis:
            result["redis"] = bool(await redis.ping())
    except Exception:
        pass
    try:
        result["worker"] = bool(await asyncio.wait_for(asyncio.to_thread(celery.control.ping, timeout=2), timeout=3))
    except Exception:
        pass
    return result
