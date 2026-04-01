from __future__ import annotations

import base64
import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from core.datetime_utils import serialize_datetime
from domain.accounts import AccountExportSelection, AccountRecord
from infrastructure.accounts_repository import AccountsRepository


CHATGPT_PLATFORM = "chatgpt"
DEFAULT_CHATGPT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


@dataclass(slots=True)
class ExportArtifact:
    filename: str
    media_type: str
    content: str | bytes | io.BytesIO


def _decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def _isoformat(value: datetime | None) -> str | None:
    return serialize_datetime(value)


def _timestamp_name(prefix: str, suffix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.{suffix}"


def _credential_value(item: AccountRecord, *keys: str) -> str:
    for key in keys:
        for credential in item.credentials or []:
            if (
                credential.get("scope") == "platform"
                and credential.get("key") == key
                and credential.get("value")
            ):
                return str(credential["value"])
    return ""


def _mailbox_provider_name(item: AccountRecord) -> str:
    for resource in item.provider_resources or []:
        if resource.get("resource_type") == "mailbox" and resource.get("provider_name"):
            return str(resource["provider_name"])
    for provider_account in item.provider_accounts or []:
        if provider_account.get("provider_type") == "mailbox" and provider_account.get(
            "provider_name"
        ):
            return str(provider_account["provider_name"])
    return ""


def _chatgpt_export_payload(item: AccountRecord) -> dict:
    access_token = _credential_value(
        item, "access_token", "accessToken", "legacy_token"
    )
    refresh_token = _credential_value(item, "refresh_token", "refreshToken")
    id_token = _credential_value(item, "id_token", "idToken")
    session_token = _credential_value(item, "session_token", "sessionToken")
    workspace_id = _credential_value(item, "workspace_id", "workspaceId")
    client_id = (
        _credential_value(item, "client_id", "clientId") or DEFAULT_CHATGPT_CLIENT_ID
    )
    cookies = _credential_value(item, "cookies", "cookie")
    account_id = item.user_id or ""
    email_service = _mailbox_provider_name(item)

    payload = _decode_jwt_payload(access_token) if access_token else {}
    auth_info = payload.get("https://api.openai.com/auth", {})
    if not account_id:
        account_id = auth_info.get("chatgpt_account_id", "") or ""
    expires_at = None
    exp_timestamp = payload.get("exp")
    if isinstance(exp_timestamp, int) and exp_timestamp > 0:
        expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    return {
        "id": item.id,
        "email": item.email,
        "password": item.password,
        "client_id": client_id,
        "account_id": account_id,
        "workspace_id": workspace_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "session_token": session_token,
        "cookies": cookies,
        "email_service": email_service,
        "registered_at": _isoformat(item.created_at),
        "last_refresh": _isoformat(item.updated_at),
        "expires_at": _isoformat(expires_at),
        "status": item.display_status,
        "expires_at_unix": int(expires_at.timestamp()) if expires_at else 0,
    }


def _to_cpa_account(item: AccountRecord) -> SimpleNamespace:
    payload = _chatgpt_export_payload(item)
    return SimpleNamespace(
        email=payload["email"],
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
        id_token=payload["id_token"],
    )


def _generate_cpa_token_json(item: AccountRecord) -> dict:
    from platforms.chatgpt.cpa_upload import generate_token_json

    return generate_token_json(_to_cpa_account(item))


def _make_sub2api_json(item: AccountRecord) -> dict:
    from datetime import datetime, timezone

    payload = _chatgpt_export_payload(item)
    credentials = {
        "access_token": payload["access_token"],
        "chatgpt_account_id": payload["account_id"],
        "chatgpt_user_id": "",
        "client_id": payload["client_id"],
        "expires_at": payload["expires_at_unix"],
        "expires_in": 863999,
        "model_mapping": {
            "gpt-5.1": "gpt-5.1",
            "gpt-5.1-codex": "gpt-5.1-codex",
            "gpt-5.1-codex-max": "gpt-5.1-codex-max",
            "gpt-5.1-codex-mini": "gpt-5.1-codex-mini",
            "gpt-5.2": "gpt-5.2",
            "gpt-5.2-codex": "gpt-5.2-codex",
        },
        "organization_id": payload["workspace_id"],
    }
    if payload["refresh_token"]:
        credentials["refresh_token"] = payload["refresh_token"]

    account_entry = {
        "name": payload["email"],
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
        "extra": {},
        "concurrency": 10,
        "priority": 1,
        "rate_multiplier": 1,
        "auto_pause_on_expired": True,
    }
    return {
        "data": {
            "type": "sub2api-data",
            "version": 1,
            "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "proxies": [],
            "accounts": [account_entry],
        }
    }


def _make_codex_cli_account(item: AccountRecord, index: int) -> dict:
    payload = _chatgpt_export_payload(item)
    return {
        "name": f"openai-codex-oauth-{index}",
        "platform": "openai",
        "type": "oauth",
        "credentials": {
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "id_token": payload["id_token"],
            "expires_at": payload["expires_at"] or "",
            "client_id": payload["client_id"],
        },
        "extra": {
            "codex_cli_only": True,
        },
    }


class AccountExportsService:
    def __init__(self, repository: AccountsRepository | None = None):
        self.repository = repository or AccountsRepository()

    def export_chatgpt_json(self, selection: AccountExportSelection) -> ExportArtifact:
        items = self._load_chatgpt_items(selection)
        content = json.dumps(
            {
                "proxies": [],
                "accounts": [
                    _make_codex_cli_account(item, index)
                    for index, item in enumerate(items, start=1)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        return ExportArtifact(
            filename=_timestamp_name("codex_accounts", "json"),
            media_type="application/json",
            content=content,
        )

    def export_chatgpt_csv(self, selection: AccountExportSelection) -> ExportArtifact:
        items = self._load_chatgpt_items(selection)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "ID",
                "Email",
                "Password",
                "Client ID",
                "Account ID",
                "Workspace ID",
                "Access Token",
                "Refresh Token",
                "ID Token",
                "Session Token",
                "Email Service",
                "Status",
                "Registered At",
                "Last Refresh",
                "Expires At",
            ]
        )
        for item in items:
            payload = _chatgpt_export_payload(item)
            writer.writerow(
                [
                    payload["id"],
                    payload["email"],
                    payload["password"],
                    payload["client_id"],
                    payload["account_id"],
                    payload["workspace_id"],
                    payload["access_token"],
                    payload["refresh_token"],
                    payload["id_token"],
                    payload["session_token"],
                    payload["email_service"],
                    payload["status"],
                    payload["registered_at"] or "",
                    payload["last_refresh"] or "",
                    payload["expires_at"] or "",
                ]
            )
        return ExportArtifact(
            filename=_timestamp_name("accounts", "csv"),
            media_type="text/csv",
            content=output.getvalue(),
        )

    def export_chatgpt_sub2api(
        self, selection: AccountExportSelection
    ) -> ExportArtifact:
        items = self._load_chatgpt_items(selection)
        if len(items) == 1:
            item = items[0]
            content = json.dumps(_make_sub2api_json(item), ensure_ascii=False, indent=2)
            return ExportArtifact(
                filename=f"{item.email}_sub2api.json",
                media_type="application/json",
                content=content,
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                archive.writestr(
                    f"{item.email}_sub2api.json",
                    json.dumps(_make_sub2api_json(item), ensure_ascii=False, indent=2),
                )
        buffer.seek(0)
        return ExportArtifact(
            filename=_timestamp_name("sub2api_tokens", "zip"),
            media_type="application/zip",
            content=buffer,
        )

    def export_chatgpt_cpa(self, selection: AccountExportSelection) -> ExportArtifact:
        items = self._load_chatgpt_items(selection)
        if len(items) == 1:
            item = items[0]
            content = json.dumps(
                _generate_cpa_token_json(item), ensure_ascii=False, indent=2
            )
            return ExportArtifact(
                filename=f"{item.email}.json",
                media_type="application/json",
                content=content,
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                archive.writestr(
                    f"{item.email}.json",
                    json.dumps(
                        _generate_cpa_token_json(item), ensure_ascii=False, indent=2
                    ),
                )
        buffer.seek(0)
        return ExportArtifact(
            filename=_timestamp_name("cpa_tokens", "zip"),
            media_type="application/zip",
            content=buffer,
        )

    def _load_chatgpt_items(
        self, selection: AccountExportSelection
    ) -> list[AccountRecord]:
        selection.platform = selection.platform or CHATGPT_PLATFORM
        if selection.platform != CHATGPT_PLATFORM:
            raise ValueError("仅支持 ChatGPT 账号导出")
        return self.repository.select_for_export(selection)
