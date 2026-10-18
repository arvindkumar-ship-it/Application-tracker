from fastapi import HTTPException, Request
from app.config import get_settings
from app.security import COOKIE_NAME, verify_session


async def require_auth(request: Request):
    token = request.cookies.get(COOKIE_NAME, "")
    if not verify_session(token, get_settings().session_secret):
        raise HTTPException(401, "Please sign in to continue")
    return {"full_name": "Arvind"}
