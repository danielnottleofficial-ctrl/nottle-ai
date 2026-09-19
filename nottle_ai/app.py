from __future__ import annotations

import html
import logging
import re
import smtplib
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .config import PROJECT_DIR, Settings
from .database import Database
from .security import (
    hash_password,
    new_token,
    normalize_email,
    public_request_url,
    sign_payload,
    validate_twilio_signature,
    verify_password,
)
from .voice import handle_media_stream


logger = logging.getLogger("nottle_ai")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
STATIC_DIR = PROJECT_DIR / "static"


class RegisterInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=200)
    business_name: str = Field(min_length=2, max_length=120)
    accept_terms: bool

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("accept_terms")
    @classmethod
    def terms_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the Terms and Privacy Policy")
        return value


class LoginInput(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class ResetRequestInput(BaseModel):
    email: str = Field(min_length=1, max_length=254)


class ResetPasswordInput(BaseModel):
    token: str = Field(min_length=20, max_length=300)
    password: str = Field(min_length=10, max_length=200)


class DeleteAccountInput(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    confirmation: str


class BusinessUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    industry: str | None = Field(default=None, max_length=120)
    area: str | None = Field(default=None, max_length=160)
    greeting: str | None = Field(default=None, max_length=240)
    services: str | None = Field(default=None, max_length=2000)
    business_hours: str | None = Field(default=None, max_length=1000)
    notification_email: str | None = Field(default=None, max_length=254)
    fallback_phone: str | None = Field(default=None, max_length=40)
    assistant_name: str | None = Field(default=None, min_length=2, max_length=40)
    voice: str | None = Field(default=None, max_length=40)
    extra_instructions: str | None = Field(default=None, max_length=2000)
    conversation_pace: str | None = None
    timezone: str | None = Field(default=None, max_length=80)
    onboarding_completed: bool | None = None

    @field_validator("conversation_pace")
    @classmethod
    def valid_pace(cls, value: str | None) -> str | None:
        if value is not None and value not in {"patient", "balanced", "fast"}:
            raise ValueError("Invalid conversation pace")
        return value

    @field_validator("voice")
    @classmethod
    def valid_voice(cls, value: str | None) -> str | None:
        if value is not None and value not in {
            "marin",
            "cedar",
            "alloy",
            "ash",
            "ballad",
            "coral",
            "echo",
            "sage",
            "shimmer",
            "verse",
        }:
            raise ValueError("Unsupported voice")
        return value


class AdminBusinessUpdateInput(BaseModel):
    phone_display: str | None = Field(default=None, max_length=40)
    phone_status: str | None = None
    subscription_status: str | None = None
    plan: str | None = None


def _user_public(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "is_admin": bool(user.get("is_admin")),
        "created_at": user["created_at"],
    }


def _business_public(business: dict[str, Any]) -> dict[str, Any]:
    result = dict(business)
    result["onboarding_completed"] = bool(result.get("onboarding_completed"))
    result.pop("is_system_default", None)
    result.pop("owner_user_id", None)
    return result


def _trial_expired(business: dict[str, Any]) -> bool:
    if business.get("subscription_status") != "trial":
        return False
    try:
        end = datetime.fromisoformat(str(business.get("trial_ends_at")))
        return end < datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return True


class RateLimiter:
    def __init__(self) -> None:
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, seconds: int) -> bool:
        now = time.monotonic()
        events = self.events[key]
        while events and events[0] < now - seconds:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


def _send_reset_email(settings: Settings, recipient: str, reset_link: str) -> None:
    if not settings.smtp_enabled:
        return
    message = EmailMessage()
    message["Subject"] = "Reset your NOTTLE AI password"
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message.set_content(
        "Use this link within one hour to reset your NOTTLE AI password:\n\n"
        f"{reset_link}\n\nIf you did not request this, you can ignore this email."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_path, settings)
    database.init()
    limiter = RateLimiter()

    app = FastAPI(
        title="NOTTLE AI",
        description="AI receptionist platform for small businesses",
        version=__version__,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.database = database

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self' https: wss:; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    def raw_bearer(request: Request) -> str:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Sign in required")
        return header.split(" ", 1)[1].strip()

    def current_user(request: Request) -> dict[str, Any]:
        token = raw_bearer(request)
        user = database.session_user(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session expired")
        request.state.session_token = token
        return user

    def current_business(
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        business = database.business_for_user(int(user["id"]))
        if not business:
            raise HTTPException(status_code=404, detail="Business profile not found")
        return business

    def admin_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Administrator access required")
        return user

    def rate_limit(request: Request, route: str, limit: int = 10) -> None:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        client = forwarded or (request.client.host if request.client else "unknown")
        if not limiter.allow(f"{route}:{client}", limit=limit, seconds=900):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")

    @app.get("/api/health")
    def health() -> JSONResponse:
        checks = {
            "database": settings.database_path.exists(),
            "openai": bool(settings.openai_api_key),
            "public_url": bool(settings.public_base_url) or not settings.is_production,
            "app_secret": settings.app_secret_is_safe or not settings.is_production,
            "twilio_signature": (
                bool(settings.twilio_auth_token)
                if settings.verify_twilio_signature
                else True
            ),
            "password_email": settings.smtp_enabled or not settings.is_production,
        }
        ready = all(checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "ok": ready,
                "service": "NOTTLE AI",
                "version": __version__,
                "checks": checks,
            },
        )

    @app.get("/api/public/config")
    def public_config() -> dict[str, Any]:
        return {
            "app_name": "NOTTLE AI",
            "tagline": "Your AI receptionist",
            "support_email": settings.support_email,
            "allow_signups": settings.allow_signups,
            "trial_days": settings.trial_days,
        }

    @app.post("/api/auth/register", status_code=201)
    def register(payload: RegisterInput, request: Request) -> dict[str, Any]:
        rate_limit(request, "register", 6)
        if not settings.allow_signups:
            raise HTTPException(status_code=403, detail="New registrations are paused")
        try:
            user, business = database.create_user_and_business(
                email=payload.email,
                password_hash=hash_password(payload.password),
                full_name=payload.full_name,
                business_name=payload.business_name,
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409, detail="An account with this email already exists"
            ) from None
        token = new_token()
        expires = database.create_session(
            token, int(user["id"]), request.headers.get("user-agent", "")
        )
        return {
            "token": token,
            "expires_at": expires,
            "user": _user_public(user),
            "business": _business_public(business),
        }

    @app.post("/api/auth/login")
    def login(payload: LoginInput, request: Request) -> dict[str, Any]:
        rate_limit(request, "login", 12)
        user = database.user_by_email(payload.email)
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect")
        token = new_token()
        expires = database.create_session(
            token, int(user["id"]), request.headers.get("user-agent", "")
        )
        business = database.business_for_user(int(user["id"]))
        return {
            "token": token,
            "expires_at": expires,
            "user": _user_public(user),
            "business": _business_public(business) if business else None,
        }

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, user: dict[str, Any] = Depends(current_user)) -> Response:
        database.revoke_session(request.state.session_token)
        return Response(status_code=204)

    @app.post("/api/auth/request-reset", status_code=202)
    def request_reset(
        payload: ResetRequestInput,
        request: Request,
        background: BackgroundTasks,
    ) -> dict[str, str]:
        rate_limit(request, "password-reset", 6)
        user = database.user_by_email(payload.email)
        if user and settings.smtp_enabled:
            token = new_token()
            database.create_password_reset(int(user["id"]), token)
            base = settings.public_base_url or str(request.base_url).rstrip("/")
            link = f"{base}/?reset={token}"
            background.add_task(_send_reset_email, settings, user["email"], link)
        return {"message": "If the account exists, reset instructions will be emailed."}

    @app.post("/api/auth/reset-password")
    def reset_password(payload: ResetPasswordInput, request: Request) -> dict[str, str]:
        rate_limit(request, "password-reset-finish", 8)
        if not database.consume_password_reset(
            payload.token, hash_password(payload.password)
        ):
            raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
        return {"message": "Password updated. You can now sign in."}

    @app.get("/api/me")
    def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        business = database.business_for_user(int(user["id"]))
        return {
            "user": _user_public(user),
            "business": _business_public(business) if business else None,
        }

    @app.get("/api/dashboard")
    def dashboard(business: dict[str, Any] = Depends(current_business)) -> dict[str, Any]:
        return {
            "stats": database.dashboard(int(business["id"])),
            "business": _business_public(business),
            "trial_expired": _trial_expired(business),
        }

    @app.get("/api/business")
    def get_business(business: dict[str, Any] = Depends(current_business)) -> dict[str, Any]:
        return {"business": _business_public(business)}

    @app.patch("/api/business")
    def update_business(
        payload: BusinessUpdateInput,
        business: dict[str, Any] = Depends(current_business),
    ) -> dict[str, Any]:
        values = payload.model_dump(exclude_unset=True)
        for key, value in list(values.items()):
            if isinstance(value, str):
                values[key] = value.strip()
        if values.get("notification_email") and not EMAIL_RE.match(
            values["notification_email"]
        ):
            raise HTTPException(status_code=422, detail="Enter a valid notification email")
        updated = database.update_business(int(business["id"]), values)
        return {"business": _business_public(updated)}

    @app.get("/api/calls")
    def calls(
        limit: int = 100,
        business: dict[str, Any] = Depends(current_business),
    ) -> dict[str, Any]:
        rows = database.calls_for_business(int(business["id"]), limit)
        return {"calls": rows}

    @app.get("/api/calls/{call_id}")
    def call_detail(
        call_id: int, business: dict[str, Any] = Depends(current_business)
    ) -> dict[str, Any]:
        row = database.call_for_business(int(business["id"]), call_id)
        if not row:
            raise HTTPException(status_code=404, detail="Call not found")
        return {"call": row}

    @app.delete("/api/calls/{call_id}", status_code=204)
    def delete_call(
        call_id: int, business: dict[str, Any] = Depends(current_business)
    ) -> Response:
        if not database.delete_call(int(business["id"]), call_id):
            raise HTTPException(status_code=404, detail="Call not found")
        return Response(status_code=204)

    @app.get("/api/account/export")
    def export_account(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        business = database.business_for_user(int(user["id"]))
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user": _user_public(user),
            "business": _business_public(business) if business else None,
            "calls": (
                database.calls_for_business(int(business["id"]), 200)
                if business
                else []
            ),
        }

    @app.delete("/api/account", status_code=204)
    def delete_account(
        payload: DeleteAccountInput,
        user: dict[str, Any] = Depends(current_user),
    ) -> Response:
        if payload.confirmation.strip().upper() != "DELETE":
            raise HTTPException(status_code=400, detail="Type DELETE to confirm")
        if not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Password is incorrect")
        database.delete_user(int(user["id"]))
        return Response(status_code=204)

    @app.get("/api/admin/businesses")
    def admin_businesses(_: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
        return {"businesses": database.admin_businesses()}

    @app.patch("/api/admin/businesses/{business_id}")
    def admin_update_business(
        business_id: int,
        payload: AdminBusinessUpdateInput,
        _: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        updated = database.admin_update_business(
            business_id, **payload.model_dump(exclude_unset=True)
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Business not found")
        return {"business": _business_public(updated)}

    @app.post("/voice")
    async def voice(request: Request) -> Response:
        form = await request.form()
        params = {str(key): str(value) for key, value in form.multi_items()}
        if settings.verify_twilio_signature:
            url = public_request_url(settings.public_base_url, str(request.url))
            if not validate_twilio_signature(
                request.headers.get("x-twilio-signature", ""),
                url,
                params,
                settings.twilio_auth_token,
            ):
                raise HTTPException(status_code=403, detail="Invalid Twilio signature")

        business = database.business_by_phone(params.get("To", ""))
        if not business:
            return Response(
                "<?xml version=\"1.0\"?><Response><Reject/></Response>",
                media_type="application/xml",
            )
        enabled = business.get("subscription_status") in {"active", "trial"}
        if _trial_expired(business):
            enabled = False
        if not settings.openai_api_key or (
            not settings.app_secret_is_safe and settings.is_production
        ):
            enabled = False
        if not enabled:
            message = html.escape(
                "Thanks for calling. The AI assistant is temporarily unavailable. "
                "Please contact the business directly or try again later."
            )
            return Response(
                f"<?xml version=\"1.0\"?><Response><Say>{message}</Say></Response>",
                media_type="application/xml",
            )

        host = request.headers.get("host", "")
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme or "https")
        base = settings.public_base_url or f"{scheme}://{host}"
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        call_sid = params.get("CallSid", "")
        signed = sign_payload(
            {
                "business_id": int(business["id"]),
                "call_sid": call_sid,
                "exp": int(time.time()) + 300,
            },
            settings.app_secret,
        )
        stream_url = html.escape(f"{ws_base}/media-stream", quote=True)
        custom = {
            "token": signed,
            "call_sid": call_sid,
            "from": params.get("From", "Unknown caller"),
            "to": params.get("To", business.get("phone_display", "")),
        }
        parameters = "".join(
            f'<Parameter name="{html.escape(key, quote=True)}" '
            f'value="{html.escape(str(value), quote=True)}" />'
            for key, value in custom.items()
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Connect><Stream url="{stream_url}">{parameters}'
            "</Stream></Connect></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    @app.websocket("/media-stream")
    async def media_stream(ws: WebSocket) -> None:
        await handle_media_stream(ws, settings=settings, database=database)

    @app.get("/manifest.json", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")

    legal_files = {
        "/privacy": "privacy.html",
        "/terms": "terms.html",
        "/support": "support.html",
        "/delete-account": "delete-account.html",
    }
    for route, filename in legal_files.items():
        app.add_api_route(
            route,
            lambda filename=filename: FileResponse(STATIC_DIR / filename),
            methods=["GET"],
            include_in_schema=False,
        )

    @app.get("/", include_in_schema=False)
    @app.get("/app", include_in_schema=False)
    def root() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
