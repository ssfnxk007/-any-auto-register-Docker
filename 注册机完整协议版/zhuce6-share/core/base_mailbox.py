"""Mailbox abstractions for zhuce6."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse
from typing import Any


def _normalize_api_base_url(value: str | None, *, default: str, label: str) -> str:
    raw = str(value or "").strip() or default
    if "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{label} is invalid: {value!r}")
    return raw.rstrip("/")


@dataclass
class MailboxAccount:
    email: str
    account_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class BaseMailbox(ABC):
    @abstractmethod
    def get_email(self) -> MailboxAccount:
        """Create or reserve an email inbox."""

    @abstractmethod
    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set[str] | None = None,
    ) -> str:
        """Poll for a 6-digit verification code."""

    @abstractmethod
    def get_current_ids(self, account: MailboxAccount) -> set[str]:
        """Return the currently visible message ids."""


class CustomMailMailbox(BaseMailbox):
    """Custom mailbox API backed by /api/generate and /api/emails/:email."""

    def __init__(self, api_url: str = "", proxy: str | None = None) -> None:
        self.api = _normalize_api_base_url(
            api_url,
            default="https://mail.wyhsd.xyz",
            label="Custom Mail API URL",
        )
        self.proxy = proxy
        self._client = None

    def _get_client(self):
        import httpx

        if self._client is None:
            self._client = httpx.Client(proxy=self.proxy, timeout=15.0, trust_env=False)
        return self._client

    def _get_messages(self, email: str) -> list[dict[str, Any]]:
        client = self._get_client()
        response = client.get(f"{self.api}/api/emails/{quote(email, safe='@')}")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def get_email(self) -> MailboxAccount:
        client = self._get_client()
        response = client.get(f"{self.api}/api/generate")
        response.raise_for_status()
        data = response.json()
        email = str(data.get("email") or "").strip()
        if not email:
            raise RuntimeError("Custom Mail generated response missing email")
        return MailboxAccount(
            email=email,
            account_id=email,
            extra={
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "custom_mail",
                    "resource_type": "mailbox",
                    "resource_identifier": email,
                    "handle": email,
                    "display_name": email,
                    "metadata": {
                        "email": email,
                        "api_url": self.api,
                    },
                },
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set[str]:
        try:
            return {
                str(item.get("id", ""))
                for item in self._get_messages(account.email)
                if item.get("id")
            }
        except Exception:
            return set()

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set[str] | None = None,
    ) -> str:
        import re
        import time

        seen = set(before_ids or [])
        start = time.time()
        pattern = re.compile(r"(?<!#)(?<!\d)(\d{6})(?!\d)")
        while time.time() - start < timeout:
            try:
                for message in self._get_messages(account.email):
                    message_id = str(message.get("id", ""))
                    if not message_id or message_id in seen:
                        continue
                    seen.add(message_id)
                    text = " ".join(
                        str(message.get(key, ""))
                        for key in ("subject", "text", "html", "content")
                    )
                    if keyword and keyword.lower() not in text.lower():
                        continue
                    match = pattern.search(text)
                    if match:
                        return match.group(1)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"wait for verification code timed out ({timeout}s)")


def create_mailbox(provider: str, proxy: str | None = None) -> BaseMailbox:
    provider_key = str(provider or "").strip().lower()
    if provider_key == "custom_mail":
        return CustomMailMailbox(proxy=proxy)
    if provider_key != "cfmail":
        raise ValueError(f"Unsupported mailbox provider: {provider}")

    from .cfmail import CfMailMailbox

    return CfMailMailbox(proxy=proxy)
