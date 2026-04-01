from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_SUB2API_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_CHATGPT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def _get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store

        return str(config_store.get(key, "") or "").strip()
    except Exception:
        return ""


def _request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = None
    request_headers = {"Accept": "application/json"}
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = Request(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        data=payload,
        headers=request_headers,
        method=method.upper(),
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(raw or f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Sub2Api 请求失败: {exc}") from exc
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Sub2Api 返回了无效 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Sub2Api 返回了非对象响应")
    return data


def _auth_headers(
    base_url: str, api_key: str, admin_email: str, admin_password: str
) -> dict[str, str]:
    if api_key:
        return {"x-api-key": api_key}
    if not admin_email or not admin_password:
        raise RuntimeError("Sub2Api 认证信息未配置")
    payload = _request_json(
        "POST",
        base_url,
        "/api/v1/auth/login",
        body={"email": admin_email, "password": admin_password},
    )
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    token = str((data or {}).get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Sub2Api 登录成功但未返回 access_token")
    return {"Authorization": f"Bearer {token}"}


def _expires_at_from_access_token(access_token: str) -> str:
    try:
        from platforms.chatgpt.cpa_upload import _decode_jwt_payload

        payload = _decode_jwt_payload(access_token)
        exp_timestamp = payload.get("exp")
        if not isinstance(exp_timestamp, int) or exp_timestamp <= 0:
            return ""
        return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def upload_to_sub2api(account: Any) -> tuple[bool, str]:
    base_url = _get_config_value("sub2api_base_url") or DEFAULT_SUB2API_BASE_URL
    api_key = _get_config_value("sub2api_api_key")
    admin_email = _get_config_value("sub2api_admin_email")
    admin_password = _get_config_value("sub2api_admin_password")
    if not api_key and not (admin_email and admin_password):
        return False, "Sub2Api API Key 或管理员账号未配置"

    access_token = str(getattr(account, "access_token", "") or "").strip()
    if not access_token:
        return False, "账号缺少 access_token"

    credentials = {
        "access_token": access_token,
        "id_token": str(getattr(account, "id_token", "") or "").strip(),
        "expires_at": _expires_at_from_access_token(access_token),
        "client_id": str(
            getattr(account, "client_id", "") or DEFAULT_CHATGPT_CLIENT_ID
        ),
    }
    refresh_token = str(getattr(account, "refresh_token", "") or "").strip()
    if refresh_token:
        credentials["refresh_token"] = refresh_token

    payload = {
        "name": str(getattr(account, "email", "") or "openai-codex-oauth"),
        "platform": "openai",
        "type": "oauth",
        "credentials": credentials,
        "extra": {"codex_cli_only": True},
    }

    try:
        headers = _auth_headers(base_url, api_key, admin_email, admin_password)
        _request_json(
            "POST", base_url, "/api/v1/admin/accounts", body=payload, headers=headers
        )
        return True, "上传成功"
    except Exception as exc:
        return False, f"上传失败: {exc}"
