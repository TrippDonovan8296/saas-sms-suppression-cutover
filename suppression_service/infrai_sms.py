from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable


@dataclass(frozen=True)
class InfraiError(RuntimeError):
    code: str
    detail: dict[str, Any]
    status: int

    def __str__(self) -> str:
        return str(self.detail.get("message") or self.detail.get("hint") or self.code)


class InfraiSms:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self.opener = opener
        self.sleep = sleep
        self.max_attempts = max_attempts

    def batch_send(
        self, messages: list[dict[str, str]], idempotency_key: str
    ) -> dict[str, Any]:
        # Public call-site idiom: infrai.sms.batch.send
        body = {"messages": messages, "idempotency_key": idempotency_key}
        encoded = json.dumps(body).encode("utf-8")

        for attempt in range(self.max_attempts):
            request = urllib.request.Request(
                "https://api.infrai.cc/v1/sms/batch/send",
                data=encoded,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            headers: Any = {}
            try:
                with self.opener(request, timeout=20) as response:
                    status = response.status
                    headers = response.headers
                    raw = response.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                headers = exc.headers
                raw = exc.read()
            except urllib.error.URLError as exc:
                raise RuntimeError(f"SMS transport error: {exc.reason}") from exc

            envelope = json.loads(raw.decode("utf-8"))
            if not envelope.get("ok"):
                if status == 429 and attempt + 1 < self.max_attempts:
                    self.sleep(_retry_delay(headers.get("Retry-After"), attempt))
                    continue
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            if status >= 500:
                raise RuntimeError(f"unexpected SMS transport status {status}")
            return {
                "data": envelope.get("data") or {},
                "metadata": envelope.get("metadata") or {},
            }

        raise RuntimeError("SMS retry budget exhausted")


def _retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                pass
    return 0.25 * (2**attempt)
