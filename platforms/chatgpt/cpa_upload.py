"""
CPA (Codex Protocol API) 上传功能
"""

import json
import base64
import logging
from typing import Tuple
from datetime import datetime, timezone, timedelta

from curl_cffi import requests as cffi_requests
from curl_cffi import CurlMime

logger = logging.getLogger(__name__)


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


def _get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store

        return config_store.get(key, "")
    except Exception:
        return ""


def generate_token_json(account) -> dict:
    """
    生成 CPA 格式的 Token JSON。
    接受任意 duck-typed 对象（需有 email, access_token, refresh_token 属性），
    expired / account_id 从 JWT 自动解码，与 chatgpt_register 逻辑一致。
    """
    email = getattr(account, "email", "")
    access_token = getattr(account, "access_token", "")
    refresh_token = getattr(account, "refresh_token", "")
    id_token = getattr(account, "id_token", "")

    expired_str = ""
    account_id = ""
    chatgpt_account_id = ""
    chatgpt_user_id = ""
    if access_token:
        payload = _decode_jwt_payload(access_token)
        auth_info = payload.get("https://api.openai.com/auth", {})
        account_id = auth_info.get("chatgpt_account_id", "")
        chatgpt_account_id = auth_info.get("chatgpt_account_id", "")
        chatgpt_user_id = auth_info.get("chatgpt_user_id", "") or auth_info.get(
            "user_id", ""
        )
        exp_timestamp = payload.get("exp")
        if isinstance(exp_timestamp, int) and exp_timestamp > 0:
            exp_dt = datetime.fromtimestamp(
                exp_timestamp, tz=timezone(timedelta(hours=8))
            )
            expired_str = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    now = datetime.now(tz=timezone(timedelta(hours=8)))
    return {
        "type": "codex",
        "email": email,
        "expired": expired_str,
        "id_token": id_token,
        "account_id": account_id,
        "chatgpt_account_id": chatgpt_account_id,
        "chatgpt_user_id": chatgpt_user_id,
        "access_token": access_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "refresh_token": refresh_token,
    }


def upload_to_cpa(
    token_data: dict,
    api_url: str = None,
    api_key: str = None,
    proxy: str = None,
) -> Tuple[bool, str]:
    """上传单个账号到 CPA 管理平台（不走代理）。
    api_url / api_key 为空时自动从 ConfigStore 读取。"""
    if not api_url:
        api_url = _get_config_value("cpa_api_url")
    if not api_key:
        api_key = _get_config_value("cpa_api_key")
    if not api_url:
        return False, "CPA API URL 未配置"

    upload_url = f"{api_url.rstrip('/')}/v0/management/auth-files"

    filename = f"{token_data['email']}.json"
    file_content = json.dumps(token_data, ensure_ascii=False, indent=2).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key or ''}",
    }

    mime = None
    try:
        mime = CurlMime()
        mime.addpart(
            name="file",
            data=file_content,
            filename=filename,
            content_type="application/json",
        )

        response = cffi_requests.post(
            upload_url,
            multipart=mime,
            headers=headers,
            proxies=None,
            verify=False,
            timeout=30,
            impersonate="chrome110",
        )

        if response.status_code in (200, 201):
            return True, "上传成功"

        error_msg = f"上传失败: HTTP {response.status_code}"
        try:
            error_detail = response.json()
            if isinstance(error_detail, dict):
                error_msg = error_detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {response.text[:200]}"
        return False, error_msg

    except Exception as e:
        logger.error(f"CPA 上传异常: {e}")
        return False, f"上传异常: {str(e)}"
    finally:
        if mime:
            mime.close()


def upload_to_team_manager(
    account,
    api_url: str = None,
    api_key: str = None,
) -> Tuple[bool, str]:
    """上传单账号到 Team Manager（直连，不走代理）。
    api_url / api_key 为空时自动从 ConfigStore 读取。"""
    if not api_url:
        api_url = _get_config_value("team_manager_url")
    if not api_key:
        api_key = _get_config_value("team_manager_key")
    if not api_url:
        return False, "Team Manager API URL 未配置"
    if not api_key:
        return False, "Team Manager API Key 未配置"

    email = getattr(account, "email", "")
    access_token = getattr(account, "access_token", "")
    if not access_token:
        return False, "账号缺少 access_token"

    url = api_url.rstrip("/") + "/api/accounts/import"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "import_type": "single",
        "email": email,
        "access_token": access_token,
        "session_token": getattr(account, "session_token", ""),
        "client_id": getattr(account, "client_id", ""),
    }
    refresh_token = getattr(account, "refresh_token", "")
    if refresh_token:
        payload["refresh_token"] = refresh_token

    try:
        resp = cffi_requests.post(
            url,
            headers=headers,
            json=payload,
            proxies=None,
            verify=False,
            timeout=30,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 201):
            return True, "上传成功"
        error_msg = f"上传失败: HTTP {resp.status_code}"
        try:
            detail = resp.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {resp.text[:200]}"
        return False, error_msg
    except Exception as e:
        logger.error(f"Team Manager 上传异常: {e}")
        return False, f"上传异常: {str(e)}"


def test_cpa_connection(
    api_url: str, api_token: str, proxy: str = None
) -> Tuple[bool, str]:
    """测试 CPA 连接（不走代理）"""
    if not api_url:
        return False, "API URL 不能为空"
    if not api_token:
        return False, "API Token 不能为空"

    api_url = api_url.rstrip("/")
    test_url = f"{api_url}/v0/management/auth-files"
    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        response = cffi_requests.options(
            test_url,
            headers=headers,
            proxies=None,
            verify=False,
            timeout=10,
            impersonate="chrome110",
        )

        if response.status_code in (200, 204, 401, 403, 405):
            if response.status_code == 401:
                return False, "连接成功，但 API Token 无效"
            return True, "CPA 连接测试成功"

        return False, f"服务器返回异常状态码: {response.status_code}"

    except cffi_requests.exceptions.ConnectionError as e:
        return False, f"无法连接到服务器: {str(e)}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查网络配置"
    except Exception as e:
        return False, f"连接测试失败: {str(e)}"
