from __future__ import annotations

import json

from suppression_service.infrai_sms import InfraiSms
from suppression_service.tenant_messaging import (
    Lifecycle,
    LifecycleChange,
    SmsSendRequest,
    SuppressionChange,
    TenantMessaging,
    TenantOnboarding,
)


def main() -> None:
    service = TenantMessaging(InfraiSms())
    service.onboard(TenantOnboarding(tenant_id="acme", admin_phone="+15550101010"))
    service.set_lifecycle("acme", LifecycleChange(lifecycle=Lifecycle.active))
    service.change_suppression(
        "acme", SuppressionChange(phone="+15550101011", suppressed=True)
    )
    result = service.send(
        SmsSendRequest(
            tenant_id="acme",
            account_id="account-42",
            phone="+15550101011",
            text="Acme: your workspace is ready.",
            event_id="onboarding-42",
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
