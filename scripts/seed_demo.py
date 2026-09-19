"""Create local-only sample data for screenshots and UI review."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from nottle_ai.config import Settings
from nottle_ai.database import Database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()

    os.environ.update(
        {
            "ENVIRONMENT": "development",
            "DATABASE_PATH": str(args.database),
            "APP_SECRET": "local-screenshot-secret-that-is-never-used-live",
            "OPENAI_API_KEY": "local-screenshot-placeholder",
            "ADMIN_EMAIL": "demo@nottle.ai",
            "ADMIN_PASSWORD": "NottleDemo2026!",
        }
    )
    settings = Settings.from_env()
    database = Database(settings.database_path, settings)
    database.init()
    user = database.user_by_email("demo@nottle.ai")
    if not user:
        raise RuntimeError("Demo administrator was not created")
    business = database.business_for_user(int(user["id"]))
    if not business:
        raise RuntimeError("Demo business was not assigned")

    database.update_business(
        int(business["id"]),
        {
            "industry": "Property services",
            "services": "Property maintenance, garden care, cleaning, project enquiries",
            "business_hours": "Monday to Friday, 7:00 am–5:00 pm",
            "greeting": "How can I help with your property today?",
            "fallback_phone": "0400 123 456",
            "onboarding_completed": True,
        },
    )
    if database.calls_for_business(int(business["id"]), 1):
        return

    samples = [
        (
            "+61 412 884 210",
            "Booking or quote request: Garden tidy-up and green waste removal in Subiaco.",
            "Caller: Hi, I'm Sarah. Could I get a quote for a garden tidy-up in Subiaco next week?\nAI: Certainly, Sarah. What is the best number for the team to call you back on?\nCaller: This number is best, thank you.",
            True,
            186,
        ),
        (
            "+61 438 221 904",
            "New customer enquiry: End-of-lease clean for a two-bedroom apartment in Perth.",
            "Caller: I'm moving out and need an end-of-lease clean for a two-bedroom apartment.\nAI: I can pass that on. Which suburb is the apartment in?\nCaller: It's in East Perth.",
            False,
            132,
        ),
        (
            "+61 401 675 332",
            "Booking or quote request: Fence repair after storm damage in Joondalup.",
            "Caller: A section of our fence came down in the storm and we'd like someone to inspect it.\nAI: Of course. Is the area currently safe?\nCaller: Yes, it is secure for now.",
            True,
            219,
        ),
        (
            "+61 466 910 725",
            "New customer enquiry: Asked whether regular commercial maintenance is available.",
            "Caller: Do you offer regular maintenance for small commercial properties?\nAI: The team can review that request and follow up with you.",
            False,
            94,
        ),
    ]
    for index, (caller, summary, transcript, booking, duration) in enumerate(samples, 1):
        call_id = database.create_call(
            business_id=int(business["id"]),
            stream_sid=f"DEMO-MS-{index}",
            call_sid=f"DEMO-CA-{index}",
            caller=caller,
            called_number=business["phone_display"],
        )
        database.finish_call(
            call_id,
            status="completed",
            transcript=transcript,
            summary=summary,
            booking_requested=booking,
            duration_seconds=duration,
        )


if __name__ == "__main__":
    main()
