from __future__ import annotations

from copy import deepcopy


CAPTCHA_POLICY = {
    "protocol_mode": "auto_first_configured_remote",
    "protocol_order": ["yescaptcha", "2captcha"],
    "browser_mode": "local_solver",
}


MAILBOX_DRIVER_TEMPLATES = [
    {
        "provider_type": "mailbox",
        "driver_type": "moemail_api",
        "label": "MoeMail API",
        "description": "MoeMail / sall.cc 协议族。优先复用你手动注册好的账号；未提供现成凭据时才自动注册 provider 账号。",
        "default_auth_mode": "username_password",
        "auth_modes": [
            {"value": "endpoint_only", "label": "仅接口地址"},
            {"value": "username_password", "label": "用户名密码"},
            {"value": "session_token", "label": "Session Token"},
            {"value": "hybrid", "label": "用户名密码 + Session Token"},
        ],
        "fields": [
            {"key": "moemail_api_url", "label": "API URL", "placeholder": "https://sall.cc", "category": "connection"},
            {"key": "moemail_username", "label": "用户名（手动注册）", "placeholder": "", "category": "auth"},
            {"key": "moemail_password", "label": "密码（手动注册）", "secret": True, "category": "auth"},
            {"key": "moemail_session_token", "label": "Session Token（可选）", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "driver_type": "tempmail_lol_api",
        "label": "TempMail.lol API",
        "description": "tempmail.lol 协议族，自动创建匿名邮箱。",
        "default_auth_mode": "anonymous",
        "auth_modes": [
            {"value": "anonymous", "label": "匿名访问"},
        ],
        "fields": [],
    },
    {
        "provider_type": "mailbox",
        "driver_type": "duckmail_api",
        "label": "DuckMail API",
        "description": "DuckMail 协议族，自动创建 provider 账号并登录获取 token。",
        "default_auth_mode": "bearer_token",
        "auth_modes": [
            {"value": "bearer_token", "label": "Bearer Token"},
        ],
        "fields": [
            {"key": "duckmail_api_url", "label": "Web URL", "placeholder": "https://www.duckmail.sbs", "category": "connection"},
            {"key": "duckmail_provider_url", "label": "Provider URL", "placeholder": "https://api.duckmail.sbs", "category": "connection"},
            {"key": "duckmail_bearer", "label": "Bearer Token", "placeholder": "kevin273945", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "driver_type": "laoudo_api",
        "label": "Laoudo API",
        "description": "Laoudo 固定邮箱协议族。",
        "default_auth_mode": "jwt_token",
        "auth_modes": [
            {"value": "jwt_token", "label": "JWT Token"},
        ],
        "fields": [
            {"key": "laoudo_email", "label": "邮箱地址", "placeholder": "xxx@laoudo.com", "category": "identity"},
            {"key": "laoudo_account_id", "label": "Account ID", "placeholder": "563", "category": "identity"},
            {"key": "laoudo_auth", "label": "JWT Token", "placeholder": "eyJ...", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "driver_type": "freemail_api",
        "label": "Freemail API",
        "description": "Freemail / Cloudflare Worker 协议族。",
        "default_auth_mode": "admin_token",
        "auth_modes": [
            {"value": "admin_token", "label": "管理员令牌"},
            {"value": "username_password", "label": "用户名密码"},
            {"value": "hybrid", "label": "令牌 + 用户名密码"},
        ],
        "fields": [
            {"key": "freemail_api_url", "label": "API URL", "placeholder": "https://mail.example.com", "category": "connection"},
            {"key": "freemail_admin_token", "label": "管理员令牌", "secret": True, "category": "auth"},
            {"key": "freemail_username", "label": "用户名（可选）", "placeholder": "", "category": "auth"},
            {"key": "freemail_password", "label": "密码（可选）", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "driver_type": "cfworker_admin_api",
        "label": "CF Worker Admin API",
        "description": "Cloudflare Worker 自建邮箱协议族。",
        "default_auth_mode": "admin_token",
        "auth_modes": [
            {"value": "admin_token", "label": "管理员 Token"},
        ],
        "fields": [
            {"key": "cfworker_api_url", "label": "API URL", "placeholder": "https://apimail.example.com", "category": "connection"},
            {"key": "cfworker_admin_token", "label": "管理员 Token", "secret": True, "category": "auth"},
            {"key": "cfworker_domain", "label": "邮箱域名", "placeholder": "example.com", "category": "connection"},
            {"key": "cfworker_fingerprint", "label": "Fingerprint", "placeholder": "6703363b...", "category": "auth"},
        ],
    },
    {
        "provider_type": "mailbox",
        "driver_type": "custom_mail_api",
        "label": "Custom Mail API",
        "description": "自建邮箱 API，支持随机生成邮箱和按邮箱查询收件列表。",
        "default_auth_mode": "endpoint_only",
        "auth_modes": [
            {"value": "endpoint_only", "label": "仅接口地址"},
        ],
        "fields": [
            {"key": "custom_mail_api_url", "label": "API URL", "placeholder": "https://mail.example.com", "category": "connection"},
        ],
    },
]


CAPTCHA_DRIVER_TEMPLATES = [
    {
        "provider_type": "captcha",
        "driver_type": "local_solver",
        "label": "本地 Solver (Camoufox)",
        "description": "本地 Turnstile Solver。",
        "default_auth_mode": "endpoint_only",
        "auth_modes": [
            {"value": "endpoint_only", "label": "仅接口地址"},
        ],
        "fields": [
            {"key": "solver_url", "label": "Solver URL", "placeholder": "http://localhost:8889", "category": "connection"},
        ],
    },
    {
        "provider_type": "captcha",
        "driver_type": "yescaptcha_api",
        "label": "YesCaptcha API",
        "description": "YesCaptcha 协议族。",
        "default_auth_mode": "api_key",
        "auth_modes": [
            {"value": "api_key", "label": "API Key"},
        ],
        "fields": [
            {"key": "yescaptcha_key", "label": "YesCaptcha Key", "secret": True, "category": "auth"},
        ],
    },
    {
        "provider_type": "captcha",
        "driver_type": "twocaptcha_api",
        "label": "2Captcha API",
        "description": "2Captcha 协议族。",
        "default_auth_mode": "api_key",
        "auth_modes": [
            {"value": "api_key", "label": "API Key"},
        ],
        "fields": [
            {"key": "twocaptcha_key", "label": "2Captcha Key", "secret": True, "category": "auth"},
        ],
    },
]


BUILTIN_PROVIDER_DEFINITIONS = [
    {
        "provider_type": "mailbox",
        "provider_key": "moemail",
        "label": "MoeMail (sall.cc)",
        "description": "优先复用你手动注册好的 MoeMail 账号；未提供凭据时退回自动注册。",
        "driver_type": "moemail_api",
    },
    {
        "provider_type": "mailbox",
        "provider_key": "tempmail_lol",
        "label": "TempMail.lol（自动生成）",
        "description": "自动生成邮箱，通常无需额外配置；如果所在网络受限，请为任务配置可用代理。",
        "driver_type": "tempmail_lol_api",
    },
    {
        "provider_type": "mailbox",
        "provider_key": "duckmail",
        "label": "DuckMail（自动生成）",
        "description": "自动生成邮箱，支持自定义 Web 地址、Provider 地址和 Bearer Token。",
        "driver_type": "duckmail_api",
    },
    {
        "provider_type": "mailbox",
        "provider_key": "laoudo",
        "label": "Laoudo（固定邮箱）",
        "description": "固定邮箱模式，需要你自己提供已有邮箱和授权信息。",
        "driver_type": "laoudo_api",
    },
    {
        "provider_type": "mailbox",
        "provider_key": "freemail",
        "label": "Freemail（自建 CF Worker）",
        "description": "基于 Cloudflare Worker 的自建邮箱，支持管理员令牌或账号密码认证。",
        "driver_type": "freemail_api",
    },
    {
        "provider_type": "mailbox",
        "provider_key": "cfworker",
        "label": "CF Worker（自建域名）",
        "description": "使用你自己的域名和 Worker 邮件服务。",
        "driver_type": "cfworker_admin_api",
    },
    {
        "provider_type": "mailbox",
        "provider_key": "custom_mail",
        "label": "Custom Mail（自建邮箱）",
        "description": "对接你自己的邮箱 API，调用 generate 与 emails 查询接口。",
        "driver_type": "custom_mail_api",
    },
    {
        "provider_type": "captcha",
        "provider_key": "local_solver",
        "label": "本地 Solver (Camoufox)",
        "description": "浏览器自动注册默认走本地 Solver。",
        "driver_type": "local_solver",
    },
    {
        "provider_type": "captcha",
        "provider_key": "yescaptcha",
        "label": "YesCaptcha",
        "description": "协议模式下优先尝试的远程打码服务。",
        "driver_type": "yescaptcha_api",
    },
    {
        "provider_type": "captcha",
        "provider_key": "2captcha",
        "label": "2Captcha",
        "description": "当 YesCaptcha 未配置时，协议模式会继续尝试 2Captcha。",
        "driver_type": "twocaptcha_api",
    },
]


def _clone(items: list[dict]) -> list[dict]:
    return deepcopy(items)


def list_driver_templates(provider_type: str) -> list[dict]:
    if provider_type == "mailbox":
        return _clone(MAILBOX_DRIVER_TEMPLATES)
    if provider_type == "captcha":
        return _clone(CAPTCHA_DRIVER_TEMPLATES)
    return []


def get_driver_template(provider_type: str, driver_type: str) -> dict | None:
    for item in list_driver_templates(provider_type):
        if item.get("driver_type") == driver_type:
            return item
    return None


def list_builtin_provider_definitions(provider_type: str | None = None) -> list[dict]:
    items = []
    for item in BUILTIN_PROVIDER_DEFINITIONS:
        if provider_type and item.get("provider_type") != provider_type:
            continue
        template = get_driver_template(str(item.get("provider_type") or ""), str(item.get("driver_type") or "")) or {}
        items.append({
            "provider_type": item.get("provider_type", ""),
            "provider_key": item.get("provider_key", ""),
            "label": item.get("label", ""),
            "description": item.get("description", ""),
            "driver_type": item.get("driver_type", ""),
            "default_auth_mode": template.get("default_auth_mode", ""),
            "auth_modes": template.get("auth_modes", []),
            "fields": template.get("fields", []),
            "enabled": True,
            "is_builtin": True,
            "metadata": {},
        })
    return items
