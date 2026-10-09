from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    environment: str
    database_path: Path
    app_secret: str
    public_base_url: str
    allowed_origins: tuple[str, ...]
    allow_signups: bool
    session_days: int
    trial_days: int

    openai_api_key: str
    openai_realtime_model: str
    openai_voice: str
    openai_transcribe_model: str

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_messaging_from: str
    sms_summary_recipient: str
    verify_twilio_signature: bool

    default_business_name: str
    default_business_phone: str
    default_business_area: str
    support_email: str
    admin_email: str
    admin_password: str

    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    trial_voice_max_calls: int = 1
    trial_voice_max_seconds: int = 60
    trial_voice_total_calls: int = 12
    play_test_limits_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        data_dir = Path(os.getenv("DATA_DIR", str(PROJECT_DIR / "data")))
        database_path = Path(os.getenv("DATABASE_PATH", str(data_dir / "nottle_ai.db")))
        database_path.parent.mkdir(parents=True, exist_ok=True)
        allowed = os.getenv(
            "ALLOWED_ORIGINS",
            "https://localhost,capacitor://localhost,http://localhost",
        )
        return cls(
            environment=environment,
            database_path=database_path,
            app_secret=os.getenv("APP_SECRET", "development-only-change-me"),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
            allowed_origins=tuple(x.strip() for x in allowed.split(",") if x.strip()),
            allow_signups=_bool("ALLOW_SIGNUPS", True),
            session_days=max(1, _int("SESSION_DAYS", 30)),
            trial_days=max(1, _int("TRIAL_DAYS", 14)),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_realtime_model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"),
            openai_voice=os.getenv("OPENAI_VOICE", "marin"),
            openai_transcribe_model=os.getenv(
                "OPENAI_TRANSCRIBE_MODEL", "gpt-live-transcribe"
            ),
            twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            twilio_messaging_from=os.getenv("TWILIO_MESSAGING_FROM", ""),
            sms_summary_recipient=os.getenv("SMS_SUMMARY_RECIPIENT", ""),
            verify_twilio_signature=_bool(
                "VERIFY_TWILIO_SIGNATURE", environment == "production"
            ),
            default_business_name=os.getenv(
                "DEFAULT_BUSINESS_NAME", "DN Property Projects"
            ),
            default_business_phone=os.getenv("DEFAULT_BUSINESS_PHONE", "08 7666 3281"),
            default_business_area=os.getenv(
                "DEFAULT_BUSINESS_AREA", "Perth, Western Australia"
            ),
            support_email=os.getenv(
                "SUPPORT_EMAIL", "DNPropertyProjects@outlook.com"
            ),
            admin_email=os.getenv("ADMIN_EMAIL", "").strip().lower(),
            admin_password=os.getenv("ADMIN_PASSWORD", ""),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=max(1, _int("SMTP_PORT", 587)),
            smtp_username=os.getenv("SMTP_USERNAME", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from=os.getenv("SMTP_FROM", "").strip(),
            trial_voice_max_calls=max(0, _int("TRIAL_VOICE_MAX_CALLS", 1)),
            trial_voice_max_seconds=max(1, _int("TRIAL_VOICE_MAX_SECONDS", 60)),
            trial_voice_total_calls=max(0, _int("TRIAL_VOICE_TOTAL_CALLS", 12)),
            play_test_limits_enabled=_bool("PLAY_TEST_LIMITS_ENABLED", True),
        )

    @property
    def sms_summary_enabled(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_messaging_from
            and self.sms_summary_recipient
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def app_secret_is_safe(self) -> bool:
        return len(self.app_secret) >= 32 and self.app_secret != "development-only-change-me"

    @property
    def smtp_enabled(self) -> bool:
        return bool(
            self.smtp_host
            and self.smtp_from
            and self.smtp_username
            and self.smtp_password
        )
