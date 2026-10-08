from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Lifecycle(str, Enum):
    onboarding = "onboarding"
    active = "active"
    suspended = "suspended"
    closed = "closed"


class TenantOnboarding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=80)
    admin_phone: str

    @field_validator("admin_phone")
    @classmethod
    def e164(cls, value: str) -> str:
        if not value.startswith("+") or not value[1:].isdigit() or not 8 <= len(value[1:]) <= 15:
            raise ValueError("admin_phone must be E.164")
        return value


class LifecycleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lifecycle: Lifecycle


class SuppressionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    suppressed: bool


class SmsSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=80)
    account_id: str = Field(min_length=1, max_length=80)
    phone: str
    text: str = Field(min_length=1, max_length=800)
    event_id: str = Field(min_length=1, max_length=120)


class SmsSender(Protocol):
    def batch_send(
        self, messages: list[dict[str, str]], idempotency_key: str
    ) -> dict[str, Any]:
        raise AssertionError("protocol method")


@dataclass
class TenantState:
    lifecycle: Lifecycle
    admin_phone: str
    inactive_accounts: set[str] = field(default_factory=set)
    suppressed_phones: set[str] = field(default_factory=set)


class TenantMessaging:
    def __init__(self, sender: SmsSender) -> None:
        self.sender = sender
        self.tenants: dict[str, TenantState] = {}

    def onboard(self, command: TenantOnboarding) -> dict[str, str]:
        self.tenants[command.tenant_id] = TenantState(
            lifecycle=Lifecycle.onboarding, admin_phone=command.admin_phone
        )
        return {"tenant_id": command.tenant_id, "lifecycle": Lifecycle.onboarding.value}

    def set_lifecycle(self, tenant_id: str, command: LifecycleChange) -> dict[str, str]:
        tenant = self._tenant(tenant_id)
        tenant.lifecycle = command.lifecycle
        return {"tenant_id": tenant_id, "lifecycle": command.lifecycle.value}

    def set_account_active(self, tenant_id: str, account_id: str, active: bool) -> dict[str, Any]:
        tenant = self._tenant(tenant_id)
        if active:
            tenant.inactive_accounts.discard(account_id)
        else:
            tenant.inactive_accounts.add(account_id)
        return {"tenant_id": tenant_id, "account_id": account_id, "active": active}

    def change_suppression(
        self, tenant_id: str, command: SuppressionChange
    ) -> dict[str, Any]:
        tenant = self._tenant(tenant_id)
        if command.suppressed:
            tenant.suppressed_phones.add(command.phone)
        else:
            tenant.suppressed_phones.discard(command.phone)
        return {"tenant_id": tenant_id, **command.model_dump()}

    def send(self, command: SmsSendRequest) -> dict[str, Any]:
        tenant = self._tenant(command.tenant_id)
        reason = self._blocked_reason(tenant, command)
        if reason:
            return {"decision": "suppressed", "reason": reason, "event_id": command.event_id}

        operation_id = f"tenant:{command.tenant_id}:event:{command.event_id}"
        result = self.sender.batch_send(
            [{"to": command.phone, "text": command.text}], operation_id
        )
        return {
            "decision": "sent",
            "event_id": command.event_id,
            "delivery": result["data"],
            "metadata": result["metadata"],
        }

    @staticmethod
    def _blocked_reason(tenant: TenantState, command: SmsSendRequest) -> str | None:
        if tenant.lifecycle not in {Lifecycle.onboarding, Lifecycle.active}:
            return "tenant_inactive"
        if command.account_id in tenant.inactive_accounts:
            return "account_inactive"
        if command.phone in tenant.suppressed_phones:
            return "recipient_opted_out"
        return None

    def _tenant(self, tenant_id: str) -> TenantState:
        try:
            return self.tenants[tenant_id]
        except KeyError as exc:
            raise KeyError(f"unknown tenant: {tenant_id}") from exc
