from urllib.parse import urlsplit
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.api import auth, health

settings = get_settings()
api_url = urlsplit(settings.next_public_api_url)
web_origin = "http://localhost:3000" if api_url.hostname in {"localhost", "127.0.0.1"} else f"{api_url.scheme}://{api_url.netloc}"
app = FastAPI(title="Arvind's Job Portal", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[web_origin], allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"])


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin != web_origin:
            return JSONResponse(status_code=403, content={"code": "origin_rejected", "message": "Request origin is not allowed", "details": None})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException):
    return JSONResponse(status_code=error.status_code, content={"code": f"http_{error.status_code}", "message": str(error.detail), "details": None})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in item["loc"]), "message": item["msg"]} for item in error.errors()]
    return JSONResponse(status_code=422, content={"code": "validation_error", "message": "Check the submitted values", "details": details})


@app.exception_handler(Exception)
async def server_error(request: Request, error: Exception):
    return JSONResponse(status_code=500, content={"code": "internal_error", "message": "The request could not be completed", "details": None})


app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
