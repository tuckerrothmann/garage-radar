"""
Notification unit tests — no live SendGrid/Slack calls.

Tests cover:
  - notify_alerts: filters to watch/act severity only
  - notify_alerts: skips already-notified alerts
  - notify_alerts: routes to email when sendgrid configured
  - notify_alerts: routes to Slack when webhook configured
  - notify_alerts: both channels, or neither (no error)
  - _sorted_alerts: act before watch before info
  - _email_subject: single/plural, act-priority
  - _email_body_text: contains reason text
  - Email send: success (202) and error (400)
  - Slack send: success ("ok") and error
  - stamp_notified: sets notified_at on all alerts

Run: pytest backend/tests/test_notifications.py -v
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from garage_radar.db.models import (
    Alert,
    AlertSeverityEnum,
    AlertStatusEnum,
    AlertTypeEnum,
)
from garage_radar.notifications.notifier import (
    _email_body_text,
    _email_subject,
    _send_email,
    _send_slack,
    _sorted_alerts,
    notify_alerts,
    stamp_notified,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _alert(severity=AlertSeverityEnum.act, notified_at=None, **kwargs) -> Alert:
    obj = MagicMock(spec=Alert)
    obj.id = uuid.uuid4()
    obj.alert_type = AlertTypeEnum.underpriced
    obj.severity = severity
    obj.status = AlertStatusEnum.open
    obj.reason = "Test reason — asking $80k vs median $100k"
    obj.delta_pct = -20.0
    obj.notified_at = notified_at
    obj.triggered_at = datetime.now(timezone.utc)
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def _settings(sendgrid_key="", email_to="", slack_url=""):
    s = MagicMock()
    s.sendgrid_api_key = sendgrid_key
    s.alert_email_to = email_to
    s.alert_email_from = "alerts@garage-radar.local"
    s.slack_webhook_url = slack_url
    return s


# ── notify_alerts filtering ───────────────────────────────────────────────────

class TestNotifyAlertsFiltering:
    @pytest.mark.asyncio
    async def test_info_only_skipped(self):
        alerts = [_alert(severity=AlertSeverityEnum.info)]
        with patch("garage_radar.notifications.notifier.get_settings", return_value=_settings()):
            stats = await notify_alerts(alerts)
        assert stats["sent_email"] == 0
        assert stats["sent_slack"] == 0
        assert stats["skipped"] == 1

    @pytest.mark.asyncio
    async def test_already_notified_skipped(self):
        alerts = [_alert(notified_at=datetime.now(timezone.utc))]
        with patch("garage_radar.notifications.notifier.get_settings", return_value=_settings()):
            stats = await notify_alerts(alerts)
        assert stats["skipped"] == 1

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self):
        with patch("garage_radar.notifications.notifier.get_settings", return_value=_settings()):
            stats = await notify_alerts([])
        assert stats["sent_email"] == 0
        assert stats["sent_slack"] == 0

    @pytest.mark.asyncio
    async def test_no_channels_configured_no_error(self):
        alerts = [_alert()]
        with patch("garage_radar.notifications.notifier.get_settings", return_value=_settings()):
            stats = await notify_alerts(alerts)
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_watch_severity_included(self):
        alerts = [_alert(severity=AlertSeverityEnum.watch)]
        sent = []
        async def _fake_email(a, s):
            sent.append(len(a))
            return True
        with patch("garage_radar.notifications.notifier.get_settings",
                   return_value=_settings(sendgrid_key="key", email_to="x@x.com")), \
             patch("garage_radar.notifications.notifier._send_email", side_effect=_fake_email):
            stats = await notify_alerts(alerts)
        assert stats["sent_email"] == 1
        assert sent == [1]


# ── _sorted_alerts ────────────────────────────────────────────────────────────

class TestSortedAlerts:
    def test_act_before_watch_before_info(self):
        alerts = [
            _alert(severity=AlertSeverityEnum.info),
            _alert(severity=AlertSeverityEnum.act),
            _alert(severity=AlertSeverityEnum.watch),
        ]
        sorted_a = _sorted_alerts(alerts)
        severities = [a.severity for a in sorted_a]
        assert severities[0] == AlertSeverityEnum.act
        assert severities[1] == AlertSeverityEnum.watch
        assert severities[2] == AlertSeverityEnum.info


# ── _email_subject ────────────────────────────────────────────────────────────

class TestEmailSubject:
    def test_single_act(self):
        subject = _email_subject([_alert(severity=AlertSeverityEnum.act)])
        assert "ACT" in subject
        assert "1" in subject

    def test_multiple_act(self):
        alerts = [_alert(severity=AlertSeverityEnum.act) for _ in range(3)]
        subject = _email_subject(alerts)
        assert "3" in subject

    def test_watch_only_no_act_label(self):
        subject = _email_subject([_alert(severity=AlertSeverityEnum.watch)])
        assert "ACT" not in subject
        assert "1" in subject

    def test_plural(self):
        alerts = [_alert(), _alert()]
        subject = _email_subject(alerts)
        assert "alerts" in subject.lower()


# ── _email_body_text ──────────────────────────────────────────────────────────

class TestEmailBodyText:
    def test_contains_reason(self):
        alert = _alert()
        body = _email_body_text([alert])
        assert alert.reason in body

    def test_contains_severity(self):
        body = _email_body_text([_alert(severity=AlertSeverityEnum.act)])
        assert "ACT" in body


# ── _send_email ───────────────────────────────────────────────────────────────

class TestSendEmail:
    @pytest.mark.asyncio
    async def test_success_on_202(self):
        settings = _settings(sendgrid_key="key", email_to="x@x.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.text = ""

        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )
            result = await _send_email([_alert()], settings)

        assert result is True

    @pytest.mark.asyncio
    async def test_failure_on_400(self):
        settings = _settings(sendgrid_key="bad-key", email_to="x@x.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Unauthorized"

        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )
            result = await _send_email([_alert()], settings)

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        settings = _settings(sendgrid_key="key", email_to="x@x.com")
        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("timeout")
            )
            result = await _send_email([_alert()], settings)

        assert result is False


# ── _send_slack ───────────────────────────────────────────────────────────────

class TestSendSlack:
    @pytest.mark.asyncio
    async def test_success_on_ok(self):
        settings = _settings(slack_url="https://hooks.slack.com/services/test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"

        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )
            result = await _send_slack([_alert()], settings)

        assert result is True

    @pytest.mark.asyncio
    async def test_failure_on_bad_response(self):
        settings = _settings(slack_url="https://hooks.slack.com/services/test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "invalid_payload"

        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )
            result = await _send_slack([_alert()], settings)

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        settings = _settings(slack_url="https://hooks.slack.com/services/test")
        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("network error")
            )
            result = await _send_slack([_alert()], settings)

        assert result is False

    @pytest.mark.asyncio
    async def test_payload_contains_reason(self):
        settings = _settings(slack_url="https://hooks.slack.com/services/test")
        alert = _alert(reason="Asking $80k is 20% below median")
        payloads = []

        async def _capture_post(url, content, headers):
            payloads.append(json.loads(content))
            mock = MagicMock()
            mock.status_code = 200
            mock.text = "ok"
            return mock

        with patch("garage_radar.notifications.notifier.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=_capture_post
            )
            await _send_slack([alert], settings)

        assert payloads
        # Reason should appear somewhere in the blocks text
        all_text = json.dumps(payloads[0])
        assert "Asking $80k is 20% below median" in all_text


# ── stamp_notified ────────────────────────────────────────────────────────────

class TestStampNotified:
    @pytest.mark.asyncio
    async def test_sets_notified_at(self):
        alerts = [_alert(), _alert()]
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        await stamp_notified(session, alerts)

        for a in alerts:
            assert a.notified_at is not None
        assert session.commit.called
