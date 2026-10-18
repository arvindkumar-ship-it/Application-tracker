import hashlib
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from app.config import get_settings
from app.deps import require_auth
from app.security import COOKIE_NAME, SESSION_SECONDS, create_session, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login")
async def login(body: Login, request: Request, response: Response):
    settings = get_settings()
    client_id = hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest()
    key = f"login-failures:{client_id}"
    try:
        async with Redis.from_url(settings.redis_url) as redis:
            failures = int(await redis.get(key) or 0)
            if failures >= 5:
                raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
            if not verify_password(body.password, settings.app_password_hash):
                await redis.eval("local n=redis.call('INCR', KEYS[1]); if n == 1 then redis.call('EXPIRE', KEYS[1], 900) end; return n", 1, key)
                raise HTTPException(401, "That password is incorrect. Please try again.")
            await redis.delete(key)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Sign-in is temporarily unavailable. Check Redis health.") from None
    secure = urlsplit(settings.next_public_api_url).scheme == "https"
    response.set_cookie(COOKIE_NAME, create_session(settings.session_secret), max_age=SESSION_SECONDS, httponly=True, samesite="lax", secure=secure, path="/")
    return {"full_name": "Arvind"}


@router.post("/logout")
async def logout(response: Response, _: dict = Depends(require_auth)):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(owner: dict = Depends(require_auth)):
    return owner
