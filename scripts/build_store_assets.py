"""Generate deterministic Google Play artwork for NOTTLE AI."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "play-store" / "assets"
PHONE = ASSETS / "phone"


DEFS = """
<defs>
  <linearGradient id="blue" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#7ad4ff"/><stop offset=".5" stop-color="#2da4f5"/><stop offset="1" stop-color="#1465c1"/></linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffe29d"/><stop offset=".5" stop-color="#efbd63"/><stop offset="1" stop-color="#a76a20"/></linearGradient>
  <radialGradient id="ambientBlue"><stop stop-color="#1e8edf" stop-opacity=".32"/><stop offset="1" stop-color="#1e8edf" stop-opacity="0"/></radialGradient>
  <radialGradient id="ambientGold"><stop stop-color="#cb852a" stop-opacity=".25"/><stop offset="1" stop-color="#cb852a" stop-opacity="0"/></radialGradient>
  <filter id="shadow" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="18" stdDeviation="24" flood-color="#000" flood-opacity=".42"/></filter>
</defs>
"""


def text(
    x: int,
    y: int,
    value: str,
    *,
    size: int = 32,
    fill: str = "#f5f7fb",
    weight: int = 500,
    anchor: str = "start",
    spacing: int = 0,
) -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="Inter,Segoe UI,Arial,sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'letter-spacing="{spacing}">{escape(value)}</text>'
    )


def rect(x: int, y: int, w: int, h: int, *, fill: str, radius: int = 28, stroke: str = "") -> str:
    border = f' stroke="{stroke}" stroke-width="2"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"{border}/>'


def mark(x: int, y: int, size: int) -> str:
    scale = size / 120
    return f"""
    <g transform="translate({x} {y}) scale({scale})">
      <path d="M24 91V29c0-7 4-11 10-11 4 0 7 2 10 6l32 44V27c0-6 4-10 10-10s10 4 10 10v64c0 7-4 11-10 11-4 0-8-2-11-6L44 53v38c0 7-4 11-10 11S24 98 24 91Z" fill="url(#blue)"/>
      <path d="M42 24 79 76V28c0-7 4-11 10-11 5 0 9 4 9 10v64c0 7-4 11-10 11-4 0-8-2-11-6L36 39c-4-6-2-14 4-17l2 2Z" fill="url(#gold)"/>
      <circle cx="103" cy="24" r="3" fill="#fff"/><path d="M103 14v5M103 29v5M93 24h5M108 24h5" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>
    </g>
    """


def phone_frame(title: str, eyebrow: str, body: str, active: str) -> str:
    nav = []
    for x, icon, label, key in (
        (135, "⌂", "Home", "home"),
        (405, "↗", "Calls", "calls"),
        (675, "✦", "Assistant", "assistant"),
        (945, "⚙", "Settings", "settings"),
    ):
        colour = "#3da9ff" if key == active else "#768296"
        nav.append(text(x, 1824, icon, size=40, fill=colour, anchor="middle"))
        nav.append(text(x, 1871, label, size=22, fill=colour, weight=650, anchor="middle"))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
    {DEFS}
    <rect width="1080" height="1920" fill="#07090d"/>
    <circle cx="30" cy="260" r="360" fill="url(#ambientBlue)"/>
    <circle cx="1080" cy="1580" r="430" fill="url(#ambientGold)"/>
    <rect x="0" y="0" width="1080" height="138" fill="#090d13"/>
    <line x1="0" y1="137" x2="1080" y2="137" stroke="#202a38" stroke-width="2"/>
    {mark(42, 25, 88)}
    {text(142, 83, "NOTTLE", size=34, weight=800, spacing=2)}
    {text(300, 83, "AI", size=34, fill="#efbd63", weight=800, spacing=2)}
    {rect(950, 39, 74, 74, fill="#17212e", radius=37, stroke="#2c3a4c")}
    {text(987, 88, "DN", size=24, weight=750, anchor="middle")}
    {text(52, 218, eyebrow, size=22, fill="#3da9ff", weight=750, spacing=3)}
    {text(52, 278, title, size=48, weight=760)}
    {body}
    <rect x="0" y="1762" width="1080" height="158" fill="#090d13"/>
    <line x1="0" y1="1762" x2="1080" y2="1762" stroke="#202a38" stroke-width="2"/>
    {''.join(nav)}
    </svg>"""


def overview() -> str:
    body = f"""
    {text(52, 328, "Here's what your receptionist has handled.", size=27, fill="#8995a7")}
    {rect(52, 376, 976, 430, fill="#0f151e", radius=34, stroke="#273648")}
    <circle cx="186" cy="530" r="93" fill="#111f2c" stroke="#3279ad" stroke-width="2"/>
    <circle cx="186" cy="530" r="67" fill="#0a1018"/>{mark(132, 476, 108)}
    <circle cx="185" cy="529" r="112" fill="none" stroke="#3da9ff" stroke-opacity=".22" stroke-width="3"/>
    {text(324, 458, "LIVE AND ANSWERING", size=21, fill="#52d997", weight=750, spacing=2)}
    {text(324, 520, "Nottle is answering", size=42, weight=760)}
    {text(324, 568, "your customer calls", size=42, weight=760)}
    {text(324, 623, "Online and ready to capture the next enquiry.", size=25, fill="#8995a7")}
    {rect(324, 668, 326, 74, fill="#1677ff", radius=20)}
    {text(487, 716, "Call your assistant  ↗", size=25, weight=700, anchor="middle")}
    {text(710, 669, "YOUR AI NUMBER", size=18, fill="#8995a7", weight=700, spacing=2)}
    {text(710, 709, "08 7666 3281", size=31, fill="#efbd63", weight=760)}
    {text(710, 741, "Perth · Available 24/7", size=20, fill="#8995a7")}
    {rect(52, 842, 230, 196, fill="#0f151e", radius=26, stroke="#202a38")}
    {rect(302, 842, 230, 196, fill="#0f151e", radius=26, stroke="#202a38")}
    {rect(552, 842, 230, 196, fill="#0f151e", radius=26, stroke="#202a38")}
    {rect(802, 842, 226, 196, fill="#0f151e", radius=26, stroke="#202a38")}
    {text(78, 892, "TOTAL CALLS", size=17, fill="#8995a7", weight=700, spacing=2)}
    {text(78, 962, "48", size=52, weight=800)}{text(78, 1004, "All time", size=21, fill="#52d997")}
    {text(328, 892, "NEW LEADS", size=17, fill="#8995a7", weight=700, spacing=2)}
    {text(328, 962, "31", size=52, weight=800)}{text(328, 1004, "Captured", size=21, fill="#efbd63")}
    {text(578, 892, "CALL TIME", size=17, fill="#8995a7", weight=700, spacing=2)}
    {text(578, 962, "2h 18m", size=42, weight=800)}{text(578, 1004, "Handled", size=21, fill="#a88cff")}
    {text(826, 892, "BOOKINGS", size=17, fill="#8995a7", weight=700, spacing=2)}
    {text(826, 962, "12", size=52, weight=800)}{text(826, 1004, "Follow up", size=21, fill="#52d997")}
    {rect(52, 1076, 976, 606, fill="#0f151e", radius=30, stroke="#202a38")}
    {text(86, 1132, "Recent calls", size=32, weight=740)}
    {text(86, 1168, "Your latest customer conversations", size=22, fill="#8995a7")}
    {call_row(86, 1214, "SA", "Sarah A.", "Garden tidy-up quote · Subiaco", "BOOKING", "3m 06s")}
    {call_row(86, 1350, "MC", "Michael C.", "End-of-lease clean · East Perth", "LEAD", "2m 12s")}
    {call_row(86, 1486, "JL", "James L.", "Fence repair after storm damage", "BOOKING", "3m 39s")}
    """
    return phone_frame("Good morning, Daniel", "OVERVIEW", body, "home")


def call_row(x: int, y: int, initials: str, name: str, summary: str, tag: str, duration: str) -> str:
    tag_fill = "#233d31" if tag == "LEAD" else "#3d3020"
    tag_text = "#52d997" if tag == "LEAD" else "#efbd63"
    return f"""
    <line x1="{x}" y1="{y + 120}" x2="994" y2="{y + 120}" stroke="#202a38" stroke-width="2"/>
    {rect(x, y + 14, 78, 78, fill="#17212e", radius=39)}
    {text(x + 39, y + 64, initials, size=24, weight=750, anchor="middle")}
    {text(x + 104, y + 45, name, size=27, weight=700)}
    {text(x + 104, y + 82, summary, size=21, fill="#8995a7")}
    {rect(796, y + 17, 126, 43, fill=tag_fill, radius=16)}
    {text(859, y + 46, tag, size=16, fill=tag_text, weight=750, anchor="middle", spacing=1)}
    {text(950, y + 88, duration, size=19, fill="#8995a7", anchor="end")}
    """


def calls() -> str:
    body = f"""
    {text(52, 328, "Review requests, contact details and clear summaries.", size=27, fill="#8995a7")}
    {rect(52, 378, 680, 82, fill="#0f151e", radius=23, stroke="#273648")}
    {text(84, 429, "⌕", size=33, fill="#657084")}{text(132, 430, "Search calls or summaries", size=24, fill="#657084")}
    {rect(754, 378, 274, 82, fill="#0f151e", radius=23, stroke="#273648")}
    {text(786, 430, "All calls", size=24)}{text(986, 430, "⌄", size=28, fill="#8995a7", anchor="end")}
    {rect(52, 498, 976, 1120, fill="#0f151e", radius=30, stroke="#202a38")}
    {text(86, 555, "TODAY", size=18, fill="#3da9ff", weight=750, spacing=2)}
    {call_row(86, 585, "SA", "Sarah Adams", "Garden tidy-up and green waste removal", "BOOKING", "3m 06s")}
    {call_row(86, 721, "MC", "Michael Chen", "End-of-lease clean for two bedrooms", "LEAD", "2m 12s")}
    {text(86, 899, "YESTERDAY", size=18, fill="#3da9ff", weight=750, spacing=2)}
    {call_row(86, 929, "JL", "James Lee", "Fence repair after storm damage", "BOOKING", "3m 39s")}
    {call_row(86, 1065, "AP", "Ava Patel", "Commercial maintenance availability", "LEAD", "1m 34s")}
    {call_row(86, 1201, "RB", "Robert Brown", "Pressure cleaning quote request", "LEAD", "2m 47s")}
    {text(86, 1406, "5 conversations", size=22, fill="#8995a7")}
    {rect(86, 1460, 908, 112, fill="#111b27", radius=22, stroke="#263a4e")}
    {text(120, 1511, "✦", size=29, fill="#efbd63")}
    {text(168, 1508, "Every enquiry stays organised", size=26, weight=700)}
    {text(168, 1543, "Open a call to review its summary and transcript.", size=21, fill="#8995a7")}
    """
    return phone_frame("Every conversation, organised", "CALLS & LEADS", body, "calls")


def call_detail() -> str:
    body = f"""
    {text(52, 328, "Call details", size=27, fill="#8995a7")}
    {rect(52, 376, 976, 1300, fill="#0f151e", radius=34, stroke="#273648")}
    {rect(86, 418, 86, 86, fill="#17212e", radius=43)}
    {text(129, 474, "SA", size=26, weight=750, anchor="middle")}
    {text(200, 456, "Sarah Adams", size=36, weight=750)}
    {text(200, 494, "Today, 9:42 am · 3m 06s", size=22, fill="#8995a7")}
    {rect(803, 432, 164, 46, fill="#3d3020", radius=17)}
    {text(885, 463, "BOOKING", size=17, fill="#efbd63", weight=750, anchor="middle", spacing=1)}
    <line x1="86" y1="544" x2="994" y2="544" stroke="#202a38" stroke-width="2"/>
    {text(86, 598, "AI SUMMARY", size=19, fill="#3da9ff", weight=750, spacing=2)}
    {rect(86, 627, 908, 198, fill="#111b27", radius=23, stroke="#263a4e")}
    {text(120, 680, "Garden tidy-up and green waste removal", size=27, weight=700)}
    {text(120, 721, "requested for a Subiaco property next week.", size=27, weight=700)}
    {text(120, 777, "Follow up to confirm access and arrange a quote.", size=22, fill="#8995a7")}
    {text(86, 898, "Transcript", size=31, weight=740)}
    {text(86, 949, "CALLER", size=17, fill="#52d997", weight=750, spacing=2)}
    {rect(86, 972, 784, 142, fill="#13221d", radius=22)}
    {text(118, 1019, "Hi, I'm Sarah. Could I get a quote for a", size=24)}
    {text(118, 1056, "garden tidy-up in Subiaco next week?", size=24)}
    {text(994, 1174, "NOTTLE AI", size=17, fill="#3da9ff", weight=750, anchor="end", spacing=2)}
    {rect(210, 1197, 784, 142, fill="#111b27", radius=22)}
    {text(242, 1244, "Certainly, Sarah. What is the best number", size=24)}
    {text(242, 1281, "for the team to call you back on?", size=24)}
    {text(86, 1399, "CALLER", size=17, fill="#52d997", weight=750, spacing=2)}
    {rect(86, 1422, 700, 100, fill="#13221d", radius=22)}
    {text(118, 1483, "This number is best, thank you.", size=24)}
    {rect(86, 1574, 290, 62, fill="#151b24", radius=18, stroke="#2c3a4c")}
    {text(231, 1615, "Delete call", size=22, fill="#ff6d7a", weight=680, anchor="middle")}
    """
    return phone_frame("Sarah Adams", "CALL DETAILS", body, "calls")


def field(x: int, y: int, w: int, label: str, value: str) -> str:
    return f"""{text(x, y, label, size=19, fill="#8995a7", weight=680)}
    {rect(x, y + 20, w, 82, fill="#0b1017", radius=18, stroke="#273648")}
    {text(x + 24, y + 72, value, size=23)}"""


def assistant() -> str:
    body = f"""
    {text(52, 328, "Teach Nottle how your business should sound.", size=27, fill="#8995a7")}
    {rect(52, 378, 976, 540, fill="#0f151e", radius=30, stroke="#202a38")}
    {rect(84, 414, 54, 54, fill="#132a3d", radius=17)}{text(111, 451, "01", size=18, fill="#3da9ff", weight=800, anchor="middle")}
    {text(160, 452, "Business profile", size=31, weight=740)}
    {field(84, 510, 438, "Business name", "DN Property Projects")}
    {field(558, 510, 438, "Industry", "Property services")}
    {field(84, 650, 912, "Service area", "Perth metropolitan area")}
    {field(84, 790, 912, "Services", "Maintenance, cleaning, garden care")}
    {rect(52, 950, 976, 600, fill="#0f151e", radius=30, stroke="#202a38")}
    {rect(84, 986, 54, 54, fill="#2e2618", radius=17)}{text(111, 1023, "02", size=18, fill="#efbd63", weight=800, anchor="middle")}
    {text(160, 1024, "Voice & conversation", size=31, weight=740)}
    {field(84, 1082, 438, "Assistant name", "Nottle")}
    {field(558, 1082, 438, "Voice", "Marin — warm & clear")}
    {field(84, 1222, 438, "Listening pace", "Patient — natural calls")}
    {field(558, 1222, 438, "Timezone", "Australia/Perth")}
    {field(84, 1362, 912, "Greeting after AI notice", "How can I help with your property today?")}
    {rect(702, 1582, 294, 76, fill="#1677ff", radius=21)}
    {text(849, 1631, "Save assistant  ✓", size=24, weight=720, anchor="middle")}
    {text(84, 1628, "All changes saved", size=21, fill="#52d997")}
    """
    return phone_frame("Make Nottle sound like your business", "ASSISTANT SETUP", body, "assistant")


def feature() -> str:
    wave = "".join(
        f'<rect x="{699 + i * 26}" y="{259 - h // 2}" width="11" height="{h}" rx="5.5" fill="{colour}" opacity="{opacity}"/>'
        for i, (h, colour, opacity) in enumerate(
            [(32, "#3da9ff", ".45"), (70, "#3da9ff", ".75"), (122, "#69c8ff", "1"), (172, "#efbd63", "1"), (114, "#efbd63", ".82"), (66, "#3da9ff", ".72"), (34, "#3da9ff", ".45")]
        )
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="500" viewBox="0 0 1024 500">
    {DEFS}
    <rect width="1024" height="500" fill="#0b1119"/>
    <circle cx="90" cy="90" r="300" fill="url(#ambientBlue)"/>
    <circle cx="960" cy="430" r="330" fill="url(#ambientGold)"/>
    <path d="M0 420C190 330 332 484 520 397s302-175 504-93V500H0Z" fill="#0f1b28" opacity=".72"/>
    {mark(70, 70, 104)}
    {text(192, 132, "NOTTLE", size=42, weight=820, spacing=3)}
    {text(380, 132, "AI", size=42, fill="#efbd63", weight=820, spacing=3)}
    {text(70, 230, "Every call answered.", size=42, weight=760)}
    {text(70, 284, "Every opportunity captured.", size=39, fill="#9acfff", weight=760)}
    {text(72, 342, "AI receptionist for calls, leads and customer enquiries.", size=21, fill="#aab5c5")}
    {rect(650, 67, 312, 116, fill="#111b27", radius=25, stroke="#2c4054")}
    <circle cx="700" cy="125" r="25" fill="#173a2b"/>{text(700, 134, "✓", size=25, fill="#52d997", weight=800, anchor="middle")}
    {text(741, 115, "AI receptionist live", size=21, weight=700)}
    {text(741, 149, "Ready for the next call", size=18, fill="#8995a7")}
    {wave}
    {rect(650, 337, 312, 90, fill="#111b27", radius=22, stroke="#2c4054")}
    {text(678, 373, "NEW ENQUIRY", size=15, fill="#efbd63", weight=750, spacing=2)}
    {text(678, 405, "Quote request captured", size=21, weight=700)}
    </svg>"""


def write_png(svg: str, path: Path, width: int, height: int, *, alpha: bool = False) -> None:
    svg = "\n".join(line.rstrip() for line in svg.splitlines()).strip() + "\n"
    svg_path = path.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(path), output_width=width, output_height=height)
    with Image.open(path) as image:
        converted = image.convert("RGBA" if alpha else "RGB")
        converted.save(path, optimize=True)


def main() -> None:
    PHONE.mkdir(parents=True, exist_ok=True)
    write_png(feature(), ASSETS / "feature-graphic-1024x500.png", 1024, 500)
    for filename, render in (
        ("01-overview-1080x1920.png", overview),
        ("02-calls-and-leads-1080x1920.png", calls),
        ("03-call-details-1080x1920.png", call_detail),
        ("04-assistant-setup-1080x1920.png", assistant),
    ):
        write_png(render(), PHONE / filename, 1080, 1920)

    icon_source = ROOT / "static" / "icons" / "icon-512.png"
    with Image.open(icon_source) as image:
        image.convert("RGBA").save(ASSETS / "icon-512.png", optimize=True)


if __name__ == "__main__":
    main()
