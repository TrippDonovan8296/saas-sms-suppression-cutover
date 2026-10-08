from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .infrai_sms import InfraiError, InfraiSms
from .tenant_messaging import (
    LifecycleChange,
    SmsSendRequest,
    SuppressionChange,
    TenantMessaging,
    TenantOnboarding,
)

app = FastAPI(title="Tenant SMS suppression service")
service: TenantMessaging | None = None


def messaging() -> TenantMessaging:
    global service
    if service is None:
        service = TenantMessaging(InfraiSms())
    return service


@app.post("/tenants", status_code=201)
def onboard(command: TenantOnboarding) -> dict[str, str]:
    return messaging().onboard(command)


@app.put("/tenants/{tenant_id}/lifecycle")
def lifecycle(tenant_id: str, command: LifecycleChange) -> dict[str, str]:
    return _call(messaging().set_lifecycle, tenant_id, command)


@app.put("/tenants/{tenant_id}/accounts/{account_id}")
def account(tenant_id: str, account_id: str, active: bool) -> dict[str, object]:
    return _call(messaging().set_account_active, tenant_id, account_id, active)


@app.put("/tenants/{tenant_id}/suppressions")
def suppression(tenant_id: str, command: SuppressionChange) -> dict[str, object]:
    return _call(messaging().change_suppression, tenant_id, command)


@app.post("/sms", status_code=202)
def send(command: SmsSendRequest) -> dict[str, object]:
    try:
        return messaging().send(command)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InfraiError as exc:
        status = exc.status if 400 <= exc.status < 500 else 502
        raise HTTPException(status_code=status, detail={"code": exc.code, **exc.detail}) from exc


def _call(function, *args):
    try:
        return function(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
