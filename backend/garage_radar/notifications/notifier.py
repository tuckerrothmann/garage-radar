"""
Garage Radar — Alert notifier.

Sends notifications for new act/watch-severity alerts via:
  - Email  (SendGrid)
  - Slack  (incoming webhook)

Design decisions:
  - Both channels are best-effort: a delivery failure is logged but never
    raises so it can't crash the scheduler or alert engine.
  - Batching: notify() accepts a list of Alert objects and groups them into
    a single email / single Slack message to avoid notification spam.
  - Dedup: we only send for alerts whose notified_at is NULL. After a
    successful send we stamp notified_at so re-runs don't re-notify.
  - Channel selection is automatic: email fires when sendgrid_api_key +
    alert_email_to are configured; Slack fires when slack_webhook_url is set.
    Either, both, or neither can be active — no error if unconfigured.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from garage_radar.config import get_settings
from garage_radar.db.models import Alert, AlertSeverityEnum

logger = logging.getLogger(__name__)

# Only notify for these severity levels
_NOTIFY_SEVERITIES = {AlertSeverityEnum.watch, AlertSeverityEnum.act}


async def notify_alerts(alerts: list[Alert]) -> dict:
    """
    Send notifications for a batch of alerts that haven't been notified yet.

    Filters to watch/act severity and unnotified alerts only.
    Returns stats: {sent_email, sent_slack, skipped, errors}.
    """
    pending = [
        a for a in alerts
        if a.severity in _NOTIFY_SEVERITIES and a.notified_at is None
    ]
    if not pending:
        return {"sent_email": 0, "sent_slack": 0, "skipped": len(alerts), "errors": 0}

    settings = get_settings()
    stats = {"sent_email": 0, "sent_slack": 0, "skipped": len(alerts) - len(pending), "errors": 0}

    # ── Email ─────────────────────────────────────────────────────────────────
    if settings.sendgrid_api_key and settings.alert_email_to:
        ok = await _send_email(pending, settings)
        if ok:
            stats["sent_email"] = 1
        else:
            stats["errors"] += 1
    else:
        logger.debug("notify: email not configured — skipping.")

    # ── Slack ─────────────────────────────────────────────────────────────────
    if settings.slack_webhook_url:
        ok = await _send_slack(pending, settings)
        if ok:
            stats["sent_slack"] = 1
        else:
            stats["errors"] += 1
    else:
        logger.debug("notify: Slack not configured — skipping.")

    return stats


async def stamp_notified(session, alerts: list[Alert]) -> None:
    """Set notified_at = now() on all alerts in the list."""
    now = datetime.now(timezone.utc)
    for alert in alerts:
        alert.notified_at = now
        session.add(alert)
    await session.commit()


# ── Email via SendGrid ────────────────────────────────────────────────────────

async def _send_email(alerts: list[Alert], settings) -> bool:
    subject = _email_subject(alerts)
    body_html = _email_body_html(alerts)
    body_text = _email_body_text(alerts)

    payload = {
        "personalizations": [{"to": [{"email": settings.alert_email_to}]}],
        "from": {"email": settings.alert_email_from},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body_text},
            {"type": "text/html",  "value": body_html},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
        if resp.status_code in (200, 202):
            logger.info("notify: email sent (%d alerts).", len(alerts))
            return True
        logger.error("notify: SendGrid returned %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.exception("notify: email send failed.")
        return False


def _email_subject(alerts: list[Alert]) -> str:
    act_count = sum(1 for a in alerts if a.severity == AlertSeverityEnum.act)
    if act_count:
        return f"🚨 Garage Radar — {act_count} ACT alert{'s' if act_count > 1 else ''} + {len(alerts) - act_count} more"
    return f"Garage Radar — {len(alerts)} new alert{'s' if len(alerts) > 1 else ''}"


def _email_body_html(alerts: list[Alert]) -> str:
    rows = ""
    for a in _sorted_alerts(alerts):
        badge_color = {"act": "#dc2626", "watch": "#d97706", "info": "#6b7280"}.get(
            a.severity.value if hasattr(a.severity, "value") else a.severity, "#6b7280"
        )
        badge = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
        alert_type = a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)
        rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb">
            <span style="background:{badge_color};color:white;padding:2px 6px;
                         border-radius:4px;font-size:11px;font-weight:bold">
              {badge.upper()}
            </span>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px">
            {alert_type.replace("_", " ").title()}
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;color:#374151">
            {a.reason}
          </td>
        </tr>"""

    return f"""
    <html><body style="font-family:sans-serif;color:#111827;max-width:700px;margin:0 auto">
      <h2 style="color:#1f2937">Garage Radar Alerts</h2>
      <p style="color:#6b7280">{len(alerts)} alert{'s' if len(alerts) > 1 else ''} triggered</p>
      <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px">
        <thead>
          <tr style="background:#f9fafb">
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280">SEVERITY</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280">TYPE</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#6b7280">DETAIL</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </body></html>"""


def _email_body_text(alerts: list[Alert]) -> str:
    lines = [f"Garage Radar — {len(alerts)} alert(s)\n"]
    for a in _sorted_alerts(alerts):
        severity = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
        alert_type = a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)
        lines.append(f"[{severity.upper()}] {alert_type}: {a.reason}")
    return "\n".join(lines)


# ── Slack ─────────────────────────────────────────────────────────────────────

async def _send_slack(alerts: list[Alert], settings) -> bool:
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🏎  Garage Radar — {len(alerts)} Alert{'s' if len(alerts) > 1 else ''}"},
        }
    ]

    for a in _sorted_alerts(alerts):
        severity = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
        alert_type = a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)
        emoji = {"act": "🚨", "watch": "👀", "info": "ℹ️"}.get(severity, "•")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{alert_type.replace('_', ' ').title()}* `{severity.upper()}`\n{a.reason}",
            },
        })
        if len(blocks) >= 48:  # Slack block limit is 50
            break

    payload = {"blocks": blocks}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.slack_webhook_url,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code == 200 and resp.text == "ok":
            logger.info("notify: Slack message sent (%d alerts).", len(alerts))
            return True
        logger.error("notify: Slack returned %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.exception("notify: Slack send failed.")
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sorted_alerts(alerts: list[Alert]) -> list[Alert]:
    """Sort act first, then watch, then info; most recent within each tier."""
    order = {"act": 0, "watch": 1, "info": 2}
    def _key(a):
        sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
        return (order.get(sev, 9), -(a.triggered_at.timestamp() if a.triggered_at else 0))
    return sorted(alerts, key=_key)
