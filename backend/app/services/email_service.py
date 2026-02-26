"""Email sending via Resend."""

import resend

from app.config import settings

resend.api_key = settings.RESEND_API_KEY


async def send_invitation_email(
    to_email: str,
    org_name: str,
    inviter_name: str,
    invite_url: str,
) -> bool:
    try:
        resend.Emails.send(
            {
                "from": settings.FROM_EMAIL,
                "to": [to_email],
                "subject": f"You've been invited to join {org_name} on humAInly",
                "html": f"""
                <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
                  <h2>You've been invited!</h2>
                  <p>{inviter_name} has invited you to join <strong>{org_name}</strong> on humAInly.</p>
                  <a href="{invite_url}"
                     style="display:inline-block;padding:12px 24px;background:#6366f1;color:#fff;
                            border-radius:6px;text-decoration:none;font-weight:600">
                    Accept Invitation
                  </a>
                  <p style="color:#888;font-size:12px;margin-top:24px">
                    This link expires in 7 days.
                  </p>
                </div>
                """,
            }
        )
        return True
    except Exception:
        return False
