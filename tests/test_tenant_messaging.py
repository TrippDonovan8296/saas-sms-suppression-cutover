from typing import Any

from suppression_service.tenant_messaging import (
    Lifecycle,
    LifecycleChange,
    SmsSendRequest,
    SuppressionChange,
    TenantMessaging,
    TenantOnboarding,
)


class RecordingSender:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], str]] = []

    def batch_send(
        self, messages: list[dict[str, str]], idempotency_key: str
    ) -> dict[str, Any]:
        self.calls.append((messages, idempotency_key))
        return {"data": {"accepted": len(messages)}, "metadata": {}}


def test_reactivation_does_not_erase_recipient_opt_out() -> None:
    sender = RecordingSender()
    service = TenantMessaging(sender)
    service.onboard(TenantOnboarding(tenant_id="acme", admin_phone="+15550101010"))
    service.set_lifecycle("acme", LifecycleChange(lifecycle=Lifecycle.active))
    service.change_suppression(
        "acme", SuppressionChange(phone="+15550101011", suppressed=True)
    )
    service.set_lifecycle("acme", LifecycleChange(lifecycle=Lifecycle.suspended))
    service.set_lifecycle("acme", LifecycleChange(lifecycle=Lifecycle.active))

    result = service.send(
        SmsSendRequest(
            tenant_id="acme",
            account_id="account-42",
            phone="+15550101011",
            text="Your workspace is ready.",
            event_id="onboarding-42",
        )
    )

    assert result == {
        "decision": "suppressed",
        "reason": "recipient_opted_out",
        "event_id": "onboarding-42",
    }
    assert sender.calls == []


def test_active_recipient_is_sent_with_stable_operation_identity() -> None:
    sender = RecordingSender()
    service = TenantMessaging(sender)
    service.onboard(TenantOnboarding(tenant_id="acme", admin_phone="+15550101010"))
    service.set_lifecycle("acme", LifecycleChange(lifecycle=Lifecycle.active))
    command = SmsSendRequest(
        tenant_id="acme",
        account_id="account-7",
        phone="+15550101012",
        text="Your invoice is ready.",
        event_id="invoice-99",
    )

    result = service.send(command)

    assert result["decision"] == "sent"
    assert sender.calls == [
        ([{"to": "+15550101012", "text": "Your invoice is ready."}], "tenant:acme:event:invoice-99")
    ]
