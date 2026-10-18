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


if __name__ == "__main__":
    from getpass import getpass
    from pathlib import Path
    import re

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        raise SystemExit("Missing .env. Copy .env.example to .env first.")
    source = env_path.read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^APP_PASSWORD_HASH=(.*)$", source)
    current = match.group(1).strip().strip("\"'") if match else ""
    if valid_password_hash(current):
        raise SystemExit("A valid password hash is already configured. No changes made.")
    password = getpass("Choose portal password (12+ characters): ")
    confirmation = getpass("Enter the same password again: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match. No changes made; run again.")
    try:
        encoded = hash_password(password)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    replacement = "APP_PASSWORD_HASH='" + encoded + "'"
    source = re.sub(r"(?m)^APP_PASSWORD_HASH=.*$", lambda _: replacement, source) if match else source + "\n" + replacement + "\n"
    env_path.write_text(source, encoding="utf-8")
    print("Password configured in .env. No password or hash was displayed.")
