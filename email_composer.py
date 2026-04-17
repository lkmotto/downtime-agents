"""
Email Composer for the DownTime Weekend Email Digest.

Generates a dark-themed HTML email + plain-text fallback.

Design system:
  Background:   #0D0D12  (deep off-black)
  Surface:      #16161F  (card background)
  Border:       #252533  (subtle divider)
  Amber accent: #F59E0B  (primary CTA color)
  Amber light:  #FCD34D  (lighter amber for body links)
  Text primary: #F0EEE8  (warm white)
  Text muted:   #9B9BAD  (secondary text)
  Camera badge: #F59E0B bg, #0D0D12 text
  Free badge:   #10B981 (emerald green)
"""
import html
import random
import os
import importlib.util
from datetime import datetime
from typing import Optional

# Load agent models by absolute path to avoid conflicts with backend models.py
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_agent_models_spec = importlib.util.spec_from_file_location(
    "agent_models",
    os.path.join(_AGENT_DIR, "models.py"),
)
_agent_models = importlib.util.module_from_spec(_agent_models_spec)  # type: ignore
_agent_models_spec.loader.exec_module(_agent_models)  # type: ignore
CuratedWeekend = _agent_models.CuratedWeekend
Event = _agent_models.Event

# ── Subject line pool ──────────────────────────────────────────────────────────

SUBJECT_TEMPLATES = [
    "Your DFW Weekend Playbook 📍",
    "10 Ways to Win This Weekend in DFW",
    "This Weekend's Best Bets in Dallas–Fort Worth",
    "Weekend Unlocked: Your DFW Hit List",
    "DFW Weekend Drop — Don't Sleep On These",
    "Your Weekend, Curated. DFW Edition.",
    "Friday's Almost Here — Here's Your Plan",
    "The DownTime DFW Weekend Guide Is In",
    "This is Your Weekend in DFW",
    "Weekend Picks, Personalized. Let's Go.",
]


def pick_subject() -> str:
    return random.choice(SUBJECT_TEMPLATES)


# ── Category icons (emoji — works in all email clients) ────────────────────────

CATEGORY_ICONS: dict[str, str] = {
    "Date Night": "🌙",
    "Adventure / Outdoors": "🏕️",
    "Food & Drink": "🍽️",
    "Arts & Culture": "🎨",
    "Free Things": "✨",
}

CATEGORY_COLORS: dict[str, str] = {
    "Date Night": "#C084FC",        # purple
    "Adventure / Outdoors": "#34D399",  # emerald
    "Food & Drink": "#FB923C",      # orange
    "Arts & Culture": "#60A5FA",    # blue
    "Free Things": "#10B981",       # green
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(text or "", quote=True)


def _format_date(time_info: str, date_start: Optional[str]) -> str:
    """Return a readable date string for display."""
    if time_info and time_info not in ("Date TBD", ""):
        return time_info
    if date_start:
        try:
            dt = datetime.fromisoformat(date_start[:19])
            return dt.strftime("%A, %B %-d at %-I:%M %p")
        except ValueError:
            return date_start
    return "This weekend"


def _camera_badge_html() -> str:
    return (
        '<span style="display:inline-block;background:#F59E0B;color:#0D0D12;'
        'font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'
        'padding:3px 8px;border-radius:4px;margin-left:8px;vertical-align:middle;">'
        '📷 Camera-Worthy</span>'
    )


def _free_badge_html() -> str:
    return (
        '<span style="display:inline-block;background:#10B981;color:#fff;'
        'font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'
        'padding:3px 8px;border-radius:4px;margin-left:8px;vertical-align:middle;">'
        'FREE</span>'
    )


def _render_event_card(event: Event, index: int) -> str:
    """Render a single event card as HTML."""
    title = _esc(event.title)
    venue = _esc(event.venue) if event.venue else ""
    city_state = ""
    if event.city:
        city_state = _esc(f"{event.city}, {event.state}" if event.state else event.city)
    date_str = _esc(_format_date(event.time_info, event.date_start))
    price = _esc(event.price_range) if event.price_range else "See link"
    why_go = _esc(event.why_go) if event.why_go else _esc(event.description[:200] + ("…" if len(event.description) > 200 else ""))
    source_url = event.source_url or "#"

    # Badges
    badges = ""
    if event.camera_worthy:
        badges += _camera_badge_html()
    if event.price_range.lower() in ("free", "$0"):
        badges += _free_badge_html()

    # Image section (only if image_url exists)
    image_html = ""
    if event.image_url:
        image_html = f'''
        <a href="{_esc(source_url)}" target="_blank" style="display:block;text-decoration:none;">
          <img src="{_esc(event.image_url)}"
               alt="{title}"
               width="560"
               style="width:100%;max-width:560px;height:180px;object-fit:cover;
                      display:block;border-radius:8px 8px 0 0;border:0;"
          />
        </a>'''

    # Card top border color based on category
    border_color = CATEGORY_COLORS.get(event.email_category, "#F59E0B")

    # Location line
    location_parts = []
    if venue:
        location_parts.append(venue)
    if city_state:
        location_parts.append(city_state)
    location_str = " · ".join(location_parts)

    cta_label = "Get Tickets" if event.price_range.lower() not in ("free", "$0", "unknown", "") else "View Details"

    card = f'''
    <!--[if mso]><table width="100%"><tr><td><![endif]-->
    <div style="background:#16161F;border-radius:10px;margin-bottom:16px;
                border:1px solid #252533;border-top:3px solid {border_color};
                overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
      {image_html}
      <div style="padding:20px 24px 22px;">

        <!-- Title row -->
        <div style="margin-bottom:6px;">
          <a href="{_esc(source_url)}" target="_blank"
             style="color:#F0EEE8;font-size:17px;font-weight:700;text-decoration:none;
                    line-height:1.3;display:inline;">{title}</a>
          {badges}
        </div>

        <!-- Meta row: date, location, price -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px;">
          <tr>
            <td style="color:#9B9BAD;font-size:13px;padding:0;vertical-align:top;">
              <span style="margin-right:14px;">🗓 {date_str}</span>
              {f'<span style="margin-right:14px;">📍 {location_str}</span>' if location_str else ''}
              <span style="color:#F59E0B;font-weight:600;">💰 {price}</span>
            </td>
          </tr>
        </table>

        <!-- Why go -->
        <p style="color:#C8C6D4;font-size:14px;line-height:1.6;margin:0 0 16px 0;">{why_go}</p>

        <!-- CTA -->
        <a href="{_esc(source_url)}" target="_blank"
           style="display:inline-block;background:#F59E0B;color:#0D0D12;
                  font-size:13px;font-weight:700;letter-spacing:0.04em;
                  text-decoration:none;padding:9px 20px;border-radius:6px;">
          {cta_label} →
        </a>

      </div>
    </div>
    <!--[if mso]></td></tr></table><![endif]-->'''

    return card


def _render_category_section(category: str, events: list[Event]) -> str:
    """Render a full category section with header + event cards."""
    icon = CATEGORY_ICONS.get(category, "📌")
    color = CATEGORY_COLORS.get(category, "#F59E0B")
    cards_html = "".join(_render_event_card(e, i) for i, e in enumerate(events))

    section = f'''
    <!-- Category: {category} -->
    <div style="margin-bottom:32px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:14px;">
        <tr>
          <td style="padding:0;">
            <span style="display:inline-block;background:{color}20;border:1px solid {color}50;
                         color:{color};font-size:11px;font-weight:700;letter-spacing:0.1em;
                         text-transform:uppercase;padding:4px 12px;border-radius:20px;">
              {icon} {_esc(category)}
            </span>
          </td>
        </tr>
      </table>
      {cards_html}
    </div>'''

    return section


def build_html_email(weekend: CuratedWeekend) -> str:
    """
    Construct the full dark-themed HTML email for the weekend digest.

    Uses inline CSS throughout for maximum email client compatibility.
    Tested against Gmail, Apple Mail, Outlook (web), and iOS Mail.
    """
    now_year = datetime.now().year
    weekend_range = f"{weekend.weekend_start} – {weekend.weekend_end}"
    city_label = _esc(weekend.city_label)

    # Render all category sections
    sections_html = "".join(
        _render_category_section(cat, events)
        for cat, events in weekend.buckets.items()
        if events
    )

    total_events = sum(len(evts) for evts in weekend.buckets.values())
    camera_count = sum(1 for e in weekend.all_events if e.camera_worthy)
    free_count = sum(1 for e in weekend.all_events if e.price_range.lower() in ("free", "$0"))

    # Stats bar
    stats_items = [f"<strong style='color:#F0EEE8;'>{total_events}</strong> picks"]
    if camera_count:
        stats_items.append(f"<strong style='color:#F59E0B;'>{camera_count}</strong> camera-worthy")
    if free_count:
        stats_items.append(f"<strong style='color:#10B981;'>{free_count}</strong> free")
    stats_html = " · ".join(stats_items)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta name="color-scheme" content="dark" />
  <meta name="supported-color-schemes" content="dark" />
  <title>DownTime — Your DFW Weekend Picks</title>
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#080810;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

<!-- Email wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:#080810;min-height:100%;padding:20px 0 40px;">
  <tr>
    <td align="center" valign="top" style="padding:0 16px;">

      <!-- Container -->
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;">

        <!-- ── HEADER ── -->
        <tr>
          <td style="padding:0 0 0 0;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="background:linear-gradient(135deg,#0D0D18 0%,#181828 100%);
                          border:1px solid #252533;border-radius:12px 12px 0 0;overflow:hidden;">
              <tr>
                <td style="padding:36px 36px 32px;">

                  <!-- Logo / wordmark -->
                  <div style="margin-bottom:24px;">
                    <span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                                 font-size:22px;font-weight:800;letter-spacing:-0.02em;color:#F0EEE8;">
                      DOWN<span style="color:#F59E0B;">TIME</span>
                    </span>
                    <span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                                 font-size:12px;font-weight:500;letter-spacing:0.1em;text-transform:uppercase;
                                 color:#9B9BAD;margin-left:10px;vertical-align:middle;">
                      Weekend Digest
                    </span>
                  </div>

                  <!-- Hero headline -->
                  <h1 style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                              font-size:30px;font-weight:800;letter-spacing:-0.02em;color:#F0EEE8;
                              margin:0 0 8px 0;line-height:1.2;">
                    This Weekend in<br/>
                    <span style="color:#F59E0B;">{city_label}</span>
                  </h1>

                  <!-- Weekend date range -->
                  <p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                             font-size:15px;color:#9B9BAD;margin:0 0 20px 0;font-weight:500;">
                    {_esc(weekend_range)}
                  </p>

                  <!-- Stats bar -->
                  <div style="background:#0D0D12;border-radius:8px;padding:12px 16px;
                               border:1px solid #252533;display:inline-block;">
                    <span style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                                 font-size:13px;color:#9B9BAD;">
                      {stats_html} · hand-picked for you
                    </span>
                  </div>

                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ── AMBER DIVIDER LINE ── -->
        <tr>
          <td style="height:3px;background:linear-gradient(90deg,#F59E0B 0%,#FCD34D 50%,#F59E0B 100%);
                     border-radius:0;">
          </td>
        </tr>

        <!-- ── CONTENT BODY ── -->
        <tr>
          <td style="background:#0D0D12;border:1px solid #252533;border-top:0;padding:32px 32px 24px;">
            {sections_html}

            <!-- ── CAMERA GEAR CALLOUT ── -->
            <div style="background:#16161F;border:1px solid #F59E0B40;border-left:3px solid #F59E0B;
                        border-radius:8px;padding:18px 20px;margin-top:8px;margin-bottom:0;">
              <p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                         font-size:13px;font-weight:700;color:#F59E0B;margin:0 0 6px 0;
                         letter-spacing:0.05em;text-transform:uppercase;">
                📷 Shooting This Weekend
              </p>
              <p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                         font-size:13px;color:#9B9BAD;margin:0;line-height:1.6;">
                Events marked <strong style="color:#F59E0B;">Camera-Worthy</strong> are
                flagged for their photo potential — great conditions for the
                <strong style="color:#C8C6D4;">Lumix S5IIX</strong>, drone, or GoPro.
                Check individual descriptions for specific shot ideas.
              </p>
            </div>
          </td>
        </tr>

        <!-- ── FOOTER ── -->
        <tr>
          <td style="background:#0A0A14;border:1px solid #252533;border-top:0;
                     border-radius:0 0 12px 12px;padding:24px 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td>
                  <!-- Footer wordmark -->
                  <p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                             font-size:14px;font-weight:700;color:#F0EEE8;margin:0 0 4px 0;">
                    DOWN<span style="color:#F59E0B;">TIME</span>
                  </p>
                  <p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                             font-size:12px;color:#9B9BAD;margin:0 0 16px 0;">
                    Personalized weekend recommendations for Dallas–Fort Worth
                  </p>

                  <!-- Divider -->
                  <div style="height:1px;background:#252533;margin-bottom:16px;"></div>

                  <!-- Legal / unsubscribe -->
                  <p style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                             font-size:11px;color:#555568;margin:0;line-height:1.7;">
                    You're receiving this because you're awesome and set this up yourself.<br/>
                    Sent every Thursday evening · {city_label} · {now_year}<br/>
                    <a href="{{{{unsubscribe_url}}}}"
                       style="color:#555568;text-decoration:underline;">Unsubscribe</a>
                    &nbsp;·&nbsp;
                    <a href="https://getdowntime.app"
                       style="color:#555568;text-decoration:underline;">getdowntime.app</a>
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
      <!-- /Container -->

    </td>
  </tr>
</table>
<!-- /Email wrapper -->

</body>
</html>"""

    return html_doc


def build_plain_text(weekend: CuratedWeekend) -> str:
    """
    Generate a plain-text fallback for the HTML email.
    Formatted for readability in plain-text email clients.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("DOWNTIME — YOUR DFW WEEKEND PICKS")
    lines.append(f"{weekend.weekend_start} – {weekend.weekend_end}")
    lines.append("=" * 60)
    lines.append("")

    total = sum(len(evts) for evts in weekend.buckets.values())
    lines.append(f"{total} picks for the weekend. Let's go.\n")

    for category, events in weekend.buckets.items():
        if not events:
            continue

        icon = CATEGORY_ICONS.get(category, "•")
        lines.append(f"{icon} {category.upper()}")
        lines.append("-" * 40)

        for event in events:
            lines.append(f"\n▸ {event.title}")

            badges = []
            if event.camera_worthy:
                badges.append("[📷 Camera-Worthy]")
            if event.price_range.lower() in ("free", "$0"):
                badges.append("[FREE]")
            if badges:
                lines.append("  " + " ".join(badges))

            date_str = _format_date(event.time_info, event.date_start)
            lines.append(f"  When:  {date_str}")

            if event.venue:
                location = event.venue
                if event.city:
                    location += f", {event.city}"
                lines.append(f"  Where: {location}")

            lines.append(f"  Price: {event.price_range or 'See link'}")

            if event.why_go:
                lines.append(f"  Why:   {event.why_go}")

            if event.source_url:
                lines.append(f"  Link:  {event.source_url}")

        lines.append("")

    lines.append("─" * 60)
    lines.append("📷 SHOOTING THIS WEEKEND")
    lines.append("Events marked [Camera-Worthy] have strong photo potential.")
    lines.append("Great conditions for the Lumix S5IIX, drone, or GoPro.")
    lines.append("")
    lines.append("─" * 60)
    lines.append("DownTime | Personalized Weekend Picks for DFW")
    lines.append("Sent every Thursday evening.")
    lines.append("Unsubscribe: {{unsubscribe_url}}")
    lines.append("=" * 60)

    return "\n".join(lines)


def compose_email(weekend: CuratedWeekend) -> dict[str, str]:
    """
    Compose the full email payload.

    Returns:
        {
            "subject": str,
            "html": str,
            "text": str,
        }
    """
    return {
        "subject": pick_subject(),
        "html": build_html_email(weekend),
        "text": build_plain_text(weekend),
    }


if __name__ == "__main__":
    """Quick preview test — outputs HTML to stdout for browser inspection."""
    from models import CuratedWeekend, Event
    from datetime import datetime

    dummy_event = Event(
        id="test_1",
        title="DFW Aerial Photography Meetup",
        description="Join fellow drone pilots and photographers at White Rock Lake.",
        category="photography",
        scenario="solo",
        source="google",
        source_url="https://example.com/event",
        venue="White Rock Lake Park",
        address="8300 E Lawther Dr",
        city="Dallas",
        state="TX",
        lat=32.826,
        lon=-96.716,
        date_start="2025-01-18T09:00:00",
        time_info="Saturday, January 18 at 9:00 AM",
        price_range="Free",
        score=87,
        camera_worthy=True,
        camera_note="Golden hour is your best friend — arrive early or stay late.",
        email_category="Free Things",
        why_go="Zero cost and seriously worth it — White Rock Lake is one of the best drone spots in DFW. Bring the S5IIX too.",
    )

    weekend = CuratedWeekend(
        fetch_date=datetime.now(),
        weekend_start="Friday, January 17",
        weekend_end="Sunday, January 19",
        city_label="Dallas–Fort Worth",
        buckets={"Free Things": [dummy_event]},
        total_fetched=120,
        total_scored=80,
    )

    result = compose_email(weekend)
    print(result["html"])
