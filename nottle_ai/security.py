from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P
    )
    return f"scrypt${PASSWORD_N}${PASSWORD_R}${PASSWORD_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError):
        return False


def new_token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_payload(token: str, secret: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def validate_twilio_signature(
    signature: str, url: str, params: dict[str, str], auth_token: str
) -> bool:
    """Validate Twilio's HMAC-SHA1 request signature without an SDK dependency."""
    if not signature or not auth_token:
        return False
    canonical = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(
        hmac.new(auth_token.encode(), canonical.encode(), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(signature, expected)


def public_request_url(base_url: str, request_url: str) -> str:
    if not base_url:
        return request_url
    parts = urlsplit(request_url)
    suffix = parts.path + (("?" + parts.query) if parts.query else "")
    return base_url.rstrip("/") + suffix


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str, country_code: str = "+61") -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return ""
    cc = "".join(ch for ch in country_code if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith(cc):
        return "+" + digits
    if digits.startswith("0") and cc:
        return "+" + cc + digits[1:]
    return "+" + digits
