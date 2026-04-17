"""
Email Sender for the DownTime Weekend Email Digest.

Uses the Resend API (resend.com) to deliver the HTML email.
API key is read from RESEND_API_KEY environment variable.

Resend docs: https://resend.com/docs/api-reference/emails/send-email
"""
import logging
import time
import os
import importlib.util
from typing import Optional
import httpx

# Load agent config by absolute path to avoid backend config shadowing
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_cfg_spec = importlib.util.spec_from_file_location("agent_config", os.path.join(_AGENT_DIR, "config.py"))
_cfg = importlib.util.module_from_spec(_cfg_spec)  # type: ignore
_cfg_spec.loader.exec_module(_cfg)  # type: ignore
RESEND_API_KEY: str = _cfg.RESEND_API_KEY
FROM_EMAIL: str = _cfg.FROM_EMAIL
RECIPIENT_EMAIL: str = _cfg.RECIPIENT_EMAIL

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


class SendError(Exception):
    """Raised when email delivery fails after all retries."""
    pass


def send_email(
    subject: str,
    html_body: str,
    text_body: str,
    to: Optional[str] = None,
    from_addr: Optional[str] = None,
) -> dict:
    """
    Send the weekend digest email via Resend.

    Args:
        subject:    Email subject line
        html_body:  Full HTML content (inline CSS)
        text_body:  Plain-text fallback
        to:         Recipient email (defaults to RECIPIENT_EMAIL from config)
        from_addr:  Sender address (defaults to FROM_EMAIL from config)

    Returns:
        Resend API response dict with `id` field

    Raises:
        SendError: If delivery fails after MAX_RETRIES attempts
        ValueError: If RESEND_API_KEY is not configured
    """
    if not RESEND_API_KEY:
        raise ValueError(
            "RESEND_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )

    recipient = to or RECIPIENT_EMAIL
    sender = from_addr or FROM_EMAIL

    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                f"Sending email to {recipient} "
                f"(attempt {attempt}/{MAX_RETRIES}): '{subject}'"
            )
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    RESEND_API_URL,
                    json=payload,
                    headers=headers,
                )

            if resp.status_code == 200 or resp.status_code == 201:
                data = resp.json()
                email_id = data.get("id", "unknown")
                logger.info(f"Email sent successfully! Resend ID: {email_id}")
                return data

            # 429 = rate limit — back off and retry
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", RETRY_BACKOFF_BASE ** attempt))
                logger.warning(f"Rate limited by Resend. Waiting {retry_after}s before retry.")
                time.sleep(retry_after)
                continue

            # 4xx errors (except 429) are not retryable
            if 400 <= resp.status_code < 500:
                error_body = resp.text
                raise SendError(
                    f"Resend API error {resp.status_code}: {error_body}"
                )

            # 5xx — retry
            logger.warning(f"Resend server error {resp.status_code}. Retrying...")
            last_error = SendError(f"Resend server error {resp.status_code}: {resp.text}")
            time.sleep(RETRY_BACKOFF_BASE ** attempt)

        except httpx.TimeoutException as e:
            logger.warning(f"Request timeout on attempt {attempt}: {e}")
            last_error = e
            time.sleep(RETRY_BACKOFF_BASE ** attempt)
        except httpx.RequestError as e:
            logger.warning(f"Network error on attempt {attempt}: {e}")
            last_error = e
            time.sleep(RETRY_BACKOFF_BASE ** attempt)
        except SendError:
            raise  # Non-retryable — bubble up immediately

    raise SendError(
        f"Failed to send email after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def send_test_email(to: Optional[str] = None) -> dict:
    """
    Send a simple test email to verify the Resend integration is working.
    Useful for CI/CD or initial setup validation.
    """
    test_subject = "DownTime Email Agent — Test"
    test_html = """
    <div style="font-family:sans-serif;background:#0D0D12;color:#F0EEE8;padding:40px;border-radius:8px;">
      <h2 style="color:#F59E0B;">✅ DownTime Email Agent is working!</h2>
      <p style="color:#9B9BAD;">This is a test email from the DownTime Weekend Digest Agent.</p>
      <p style="color:#9B9BAD;">The cron job is configured correctly and Resend integration is live.</p>
    </div>
    """
    test_text = "DownTime Email Agent is working!\n\nThis is a test email confirming the Resend integration is live."

    return send_email(
        subject=test_subject,
        html_body=test_html,
        text_body=test_text,
        to=to,
    )


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    test_to = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        result = send_test_email(to=test_to)
        print(f"Test email sent. Resend ID: {result.get('id')}")
    except (SendError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
