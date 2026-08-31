"""Fan-out, delivery failure, idempotency, and revoked webhooks (Task 15).

Send is injected. notifications/ must not import connectors/ or db.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.notification import NotificationChannel, NotificationPreview


def _channel(channel_id: str, *, revoked: bool = False) -> NotificationChannel:
    return NotificationChannel.model_validate(
        {
            "id": channel_id,
            "transport": "slack",
            "purpose": "security_alert",
            "confidentiality": "restricted",
            "revoked": revoked,
        }
    )


def _preview() -> NotificationPreview:
    from pr_reviewer.notifications.preview import build_preview

    finding = Finding(
        id="finding-1",
        review_job_id="job-1",
        concern="security",
        severity="high",
        category="sql-injection",
        file_path="src/auth.ts",
        line_start=42,
        line_end=42,
        title="SQL injection in auth.ts line 42",
        rationale="User input reaches SQL text.",
        evidence=["src/auth.ts:42"],
        confidence=0.9,
        verified=True,
        verification_method="static",
        public_safe=False,
        status="queued_for_human",
    )
    return build_preview(finding, confidentiality="restricted")


def test_partial_fan_out_records_failure_and_still_sends_the_rest() -> None:
    from pr_reviewer.notifications.dispatch import SendResult, dispatch_notifications

    calls: list[str] = []

    def send(channel: NotificationChannel, preview: NotificationPreview) -> SendResult:
        del preview
        calls.append(channel.id)
        if channel.id == "bad":
            return SendResult(ok=False, error_kind="delivery_failed")
        return SendResult(ok=True)

    result = dispatch_notifications(
        _preview(),
        [_channel("bad"), _channel("good")],
        send,
        idempotency_key="job-1:finding-1",
    )
    assert calls == ["bad", "good"]
    by_id = {item.channel_id: item for item in result.deliveries}
    assert by_id["bad"].ok is False
    assert by_id["bad"].error_kind == "delivery_failed"
    assert by_id["good"].ok is True


def test_delivery_failure_does_not_raise_out_of_fan_out() -> None:
    from pr_reviewer.notifications.dispatch import SendResult, dispatch_notifications

    def send(channel: NotificationChannel, preview: NotificationPreview) -> SendResult:
        del channel, preview
        raise RuntimeError("slack 500")

    result = dispatch_notifications(
        _preview(),
        [_channel("only")],
        send,
        idempotency_key="job-1:finding-1",
    )
    assert result.deliveries[0].ok is False
    assert result.deliveries[0].error_kind == "delivery_failed"


def test_duplicate_idempotency_key_does_not_send_again() -> None:
    from pr_reviewer.notifications.dispatch import SendResult, dispatch_notifications

    calls: list[str] = []

    def send(channel: NotificationChannel, preview: NotificationPreview) -> SendResult:
        del preview
        calls.append(channel.id)
        return SendResult(ok=True)

    seen: set[tuple[str, str]] = set()
    first = dispatch_notifications(
        _preview(),
        [_channel("ops")],
        send,
        idempotency_key="job-1:finding-1",
        seen_keys=seen,
    )
    second = dispatch_notifications(
        _preview(),
        [_channel("ops")],
        send,
        idempotency_key="job-1:finding-1",
        seen_keys=seen,
    )
    assert calls == ["ops"]
    assert first.deliveries[0].ok is True
    assert second.deliveries[0].ok is True
    assert second.deliveries[0].error_kind == "duplicate"


def test_revoked_webhook_is_not_called() -> None:
    from pr_reviewer.notifications.dispatch import SendResult, dispatch_notifications

    calls: list[str] = []

    def send(channel: NotificationChannel, preview: NotificationPreview) -> SendResult:
        del preview
        calls.append(channel.id)
        return SendResult(ok=True)

    result = dispatch_notifications(
        _preview(),
        [_channel("dead", revoked=True), _channel("live")],
        send,
        idempotency_key="job-1:finding-1",
    )
    assert calls == ["live"]
    by_id = {item.channel_id: item for item in result.deliveries}
    assert by_id["dead"].ok is False
    assert by_id["dead"].error_kind == "revoked"
    assert by_id["live"].ok is True


def test_retry_after_partial_fan_out_skips_already_sent_channel() -> None:
    from pr_reviewer.notifications.dispatch import SendResult, dispatch_notifications

    calls: list[str] = []

    def send(channel: NotificationChannel, preview: NotificationPreview) -> SendResult:
        del preview
        calls.append(channel.id)
        if channel.id == "flaky" and calls.count("flaky") == 1:
            return SendResult(ok=False, error_kind="delivery_failed")
        return SendResult(ok=True)

    seen: set[tuple[str, str]] = set()
    channels = [_channel("flaky"), _channel("stable")]
    dispatch_notifications(
        _preview(),
        channels,
        send,
        idempotency_key="job-1:finding-1",
        seen_keys=seen,
    )
    dispatch_notifications(
        _preview(),
        channels,
        send,
        idempotency_key="job-1:finding-1",
        seen_keys=seen,
    )
    assert calls == ["flaky", "stable", "flaky"]
