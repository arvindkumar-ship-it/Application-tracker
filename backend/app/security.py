import base64
import hashlib
import hmac
import secrets
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

COOKIE_NAME = "portal_session"
SESSION_SECONDS = 14 * 24 * 60 * 60
ITERATIONS = 600_000


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Use a password with at least 12 characters")
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join(("pbkdf2_sha256", str(ITERATIONS), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))


def valid_password_hash(encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$")
        return algorithm == "pbkdf2_sha256" and 600_000 <= int(iterations) <= 2_000_000 and len(base64.b64decode(salt, validate=True)) >= 16 and len(base64.b64decode(digest, validate=True)) == 32
    except (ValueError, TypeError):
        return False


def verify_password(password: str, encoded: str) -> bool:
    if not valid_password_hash(encoded):
        return False
    _, iterations, salt, digest = encoded.split("$")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def create_session(secret: str) -> str:
    return URLSafeTimedSerializer(secret, salt="portal-session").dumps({"owner": "Arvind"})


def verify_session(token: str, secret: str) -> bool:
    try:
        return URLSafeTimedSerializer(secret, salt="portal-session").loads(token, max_age=SESSION_SECONDS) == {"owner": "Arvind"}
    except (BadSignature, SignatureExpired):
        return False
