"""邮箱池基类 - 抽象临时邮箱/收件服务"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import html
import re
from urllib.parse import urlencode, urlparse


@dataclass
class MailboxAccount:
    email: str
    account_id: str = ""
    extra: dict = None  # 平台额外信息


class BaseMailbox(ABC):
    @abstractmethod
    def get_email(self) -> MailboxAccount:
        """获取一个可用邮箱"""
        ...

    @abstractmethod
    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None,
                      code_pattern: str = None) -> str:
        """等待并返回验证码，code_pattern 为自定义正则（默认匹配6位数字）"""
        ...

    @abstractmethod
    def get_current_ids(self, account: MailboxAccount) -> set:
        """返回当前邮件 ID 集合（用于过滤旧邮件）"""
        ...

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        """等待并返回验证链接。默认由具体 provider 自行实现。"""
        raise NotImplementedError(f"{self.__class__.__name__} 暂不支持 wait_for_link()")


def _extract_verification_link(text: str, keyword: str = "") -> str | None:
    combined = str(text or "")
    lowered = combined.lower()
    if keyword and keyword.lower() not in lowered:
        return None

    urls = [
        html.unescape(raw).rstrip(").,;")
        for raw in re.findall(r'https?://[^\s<>"\']+', combined, re.IGNORECASE)
    ]
    if not urls:
        return None

    primary_link_hints = ("verif", "confirm", "magic", "auth", "callback", "signin", "signup", "continue")
    primary_host_hints = ("tavily", "firecrawl", "clerk", "stytch", "auth", "login")
    for url in urls:
        url_lower = url.lower()
        if any(token in url_lower for token in primary_link_hints) and any(host in url_lower for host in primary_host_hints):
            return url

    verification_hints = ("verify", "verification", "confirm", "magic link", "sign in", "login", "auth", "tavily", "firecrawl")
    if not any(token in lowered for token in verification_hints):
        return None

    for url in urls:
        url_lower = url.lower()
        if any(token in url_lower for token in primary_link_hints):
            return url

    return urls[0]


def _normalize_api_base_url(value: str | None, *, default: str, label: str) -> str:
    raw = str(value or "").strip() or default
    if "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{label} 无效: {value!r}")
    return raw.rstrip("/")


def _create_tempmail(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return TempMailLolMailbox(proxy=proxy)


def _create_duckmail(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return DuckMailMailbox(
        api_url=extra.get("duckmail_api_url", "https://www.duckmail.sbs"),
        provider_url=extra.get("duckmail_provider_url", "https://api.duckmail.sbs"),
        bearer=extra.get("duckmail_bearer", "kevin273945"),
        proxy=proxy,
    )


def _create_freemail(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return FreemailMailbox(
        api_url=extra.get("freemail_api_url", ""),
        admin_token=extra.get("freemail_admin_token", ""),
        username=extra.get("freemail_username", ""),
        password=extra.get("freemail_password", ""),
        proxy=proxy,
    )


def _create_moemail(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return MoeMailMailbox(
        api_url=extra.get("moemail_api_url"),
        username=extra.get("moemail_username", ""),
        password=extra.get("moemail_password", ""),
        session_token=extra.get("moemail_session_token", ""),
        proxy=proxy,
    )


def _create_cfworker(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return CFWorkerMailbox(
        api_url=extra.get("cfworker_api_url", ""),
        admin_token=extra.get("cfworker_admin_token", ""),
        domain=extra.get("cfworker_domain", ""),
        fingerprint=extra.get("cfworker_fingerprint", ""),
        proxy=proxy,
    )


def _create_laoudo(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return LaoudoMailbox(
        auth_token=extra.get("laoudo_auth", ""),
        email=extra.get("laoudo_email", ""),
        account_id=extra.get("laoudo_account_id", ""),
    )


def _create_custom_mail(extra: dict, proxy: str | None) -> 'BaseMailbox':
    return CustomMailMailbox(
        api_url=extra.get("custom_mail_api_url", ""),
        proxy=proxy,
    )


MAILBOX_FACTORY_REGISTRY = {
    "tempmail_lol_api": _create_tempmail,
    "duckmail_api": _create_duckmail,
    "freemail_api": _create_freemail,
    "moemail_api": _create_moemail,
    "cfworker_admin_api": _create_cfworker,
    "laoudo_api": _create_laoudo,
    "custom_mail_api": _create_custom_mail,
    # backward-compat fallback
    "tempmail_lol": _create_tempmail,
    "duckmail": _create_duckmail,
    "freemail": _create_freemail,
    "moemail": _create_moemail,
    "cfworker": _create_cfworker,
    "laoudo": _create_laoudo,
    "custom_mail": _create_custom_mail,
}


def create_mailbox(provider: str, extra: dict = None, proxy: str = None) -> 'BaseMailbox':
    """工厂方法：根据 provider 创建对应的 mailbox 实例"""
    from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository
    from infrastructure.provider_settings_repository import ProviderSettingsRepository

    provider_key = str(provider or "moemail")
    definition = ProviderDefinitionsRepository().get_by_key("mailbox", provider_key)
    resolved_extra = ProviderSettingsRepository().resolve_runtime_settings("mailbox", provider_key, extra or {})
    lookup_key = definition.driver_type if definition else provider_key
    factory = MAILBOX_FACTORY_REGISTRY.get(lookup_key, _create_laoudo)
    return factory(resolved_extra, proxy)


class LaoudoMailbox(BaseMailbox):
    """laoudo.com 邮箱服务"""
    def __init__(self, auth_token: str, email: str, account_id: str):
        self.auth = auth_token
        self._email = email
        self._account_id = account_id
        self.api = "https://laoudo.com/api/email"
        self._ua = "Mozilla/5.0"

    def get_email(self) -> MailboxAccount:
        return MailboxAccount(
            email=self._email,
            account_id=self._account_id,
            extra={
                "provider_account": {
                    "provider_type": "mailbox",
                    "provider_name": "laoudo",
                    "login_identifier": self._email,
                    "display_name": self._email,
                    "credentials": {
                        "authorization": self.auth,
                    },
                    "metadata": {
                        "account_id": self._account_id,
                        "email": self._email,
                    },
                },
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "laoudo",
                    "resource_type": "mailbox",
                    "resource_identifier": self._account_id,
                    "handle": self._email,
                    "display_name": self._email,
                    "metadata": {
                        "account_id": self._account_id,
                        "email": self._email,
                    },
                },
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        from curl_cffi import requests as curl_requests
        try:
            r = curl_requests.get(
                f"{self.api}/list",
                params={"accountId": account.account_id, "allReceive": 0,
                        "emailId": 0, "timeSort": 1, "size": 50, "type": 0},
                headers={"authorization": self.auth, "user-agent": self._ua},
                timeout=15, impersonate="chrome131"
            )
            if r.status_code == 200:
                mails = r.json().get("data", {}).get("list", []) or []
                return {m.get("id") or m.get("emailId") for m in mails if m.get("id") or m.get("emailId")}
        except Exception:
            pass
        return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "trae",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re, time
        from curl_cffi import requests as curl_requests
        seen = set(before_ids) if before_ids else set()
        start = time.time()
        h = {"authorization": self.auth, "user-agent": self._ua}
        while time.time() - start < timeout:
            try:
                r = curl_requests.get(
                    f"{self.api}/list",
                    params={"accountId": account.account_id, "allReceive": 0,
                            "emailId": 0, "timeSort": 1, "size": 50, "type": 0},
                    headers=h, timeout=15, impersonate="chrome131"
                )
                if r.status_code == 200:
                    mails = r.json().get("data", {}).get("list", []) or []
                    for mail in mails:
                        mid = mail.get("id") or mail.get("emailId")
                        if not mid or mid in seen:
                            continue
                        seen.add(mid)
                        text = (str(mail.get("subject", "")) + " " +
                                str(mail.get("content") or mail.get("html") or ""))
                        if keyword and keyword.lower() not in text.lower():
                            continue
                        m = re.search(code_pattern or r'(?<!#)(?<!\d)(\d{6})(?!\d)', text)
                        if m:
                            return m.group(1) if m.groups() else m.group(0)
            except Exception:
                pass
            time.sleep(4)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time
        from curl_cffi import requests as curl_requests
        seen = set(before_ids or [])
        start = time.time()
        headers = {"authorization": self.auth, "user-agent": self._ua}
        while time.time() - start < timeout:
            try:
                r = curl_requests.get(
                    f"{self.api}/list",
                    params={"accountId": account.account_id, "allReceive": 0,
                            "emailId": 0, "timeSort": 1, "size": 50, "type": 0},
                    headers=headers, timeout=15, impersonate="chrome131"
                )
                if r.status_code == 200:
                    mails = r.json().get("data", {}).get("list", []) or []
                    for mail in mails:
                        mid = mail.get("id") or mail.get("emailId")
                        if not mid or mid in seen:
                            continue
                        seen.add(mid)
                        text = (str(mail.get("subject", "")) + " " +
                                str(mail.get("content") or mail.get("html") or ""))
                        link = _extract_verification_link(text, keyword)
                        if link:
                            return link
            except Exception:
                pass
            time.sleep(4)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class CustomMailMailbox(BaseMailbox):
    """自建邮箱 API，要求提供 /api/generate 与 /api/emails/:email。"""

    def __init__(self, api_url: str, proxy: str = None):
        self.api = _normalize_api_base_url(api_url, default="https://mail.wyhsd.xyz", label="Custom Mail API URL")
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self._session = None

    def _get_session(self):
        import requests

        if self._session is None:
            session = requests.Session()
            session.proxies = self.proxy
            self._session = session
        return self._session

    def _get_messages(self, email: str) -> list[dict]:
        session = self._get_session()
        from urllib.parse import quote

        resp = session.get(f"{self.api}/api/emails/{quote(email, safe='@')}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    def get_email(self) -> MailboxAccount:
        session = self._get_session()
        resp = session.get(f"{self.api}/api/generate", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        email = str(data.get("email") or "").strip()
        if not email:
            raise RuntimeError("Custom Mail 生成邮箱失败: 返回结果缺少 email")
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

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            return {str(item.get("id", "")) for item in self._get_messages(account.email) if item.get("id")}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re
        import time

        seen = set(before_ids or [])
        start = time.time()
        pattern = re.compile(code_pattern or r'(?<!#)(?<!\d)(\d{6})(?!\d)')
        while time.time() - start < timeout:
            try:
                for msg in self._get_messages(account.email):
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    text = " ".join(str(msg.get(key, "")) for key in ("subject", "text", "html"))
                    if keyword and keyword.lower() not in text.lower():
                        continue
                    match = pattern.search(text)
                    if match:
                        return match.group(1) if match.groups() else match.group(0)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time

        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                for msg in self._get_messages(account.email):
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    text = " ".join(str(msg.get(key, "")) for key in ("subject", "text", "html"))
                    link = _extract_verification_link(text, keyword)
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class AitreMailbox(BaseMailbox):
    """mail.aitre.cc 临时邮箱"""
    def __init__(self, email: str):
        self._email = email
        self.api = "https://mail.aitre.cc/api/tempmail"

    def get_email(self) -> MailboxAccount:
        return MailboxAccount(email=self._email)

    def get_current_ids(self, account: MailboxAccount) -> set:
        import requests
        try:
            r = requests.get(f"{self.api}/emails", params={"email": account.email}, timeout=10)
            emails = r.json().get("emails", [])
            return {str(m["id"]) for m in emails if "id" in m}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "trae",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re, time, requests
        seen = set(before_ids) if before_ids else set()
        last_check = None
        start = time.time()
        while time.time() - start < timeout:
            params = {"email": account.email}
            if last_check:
                params["lastCheck"] = last_check
            try:
                r = requests.get(f"{self.api}/poll", params=params, timeout=10)
                data = r.json()
                last_check = data.get("lastChecked")
                if data.get("count", 0) > 0:
                    r2 = requests.get(f"{self.api}/emails", params={"email": account.email}, timeout=10)
                    for mail in r2.json().get("emails", []):
                        mid = str(mail.get("id", ""))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        text = mail.get("preview", "") + mail.get("content", "")
                        if keyword and keyword.lower() not in text.lower():
                            continue
                        m = re.search(code_pattern or r'(?<!#)(?<!\d)(\d{6})(?!\d)', text)
                        if m:
                            return m.group(1) if m.groups() else m.group(0)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time, requests
        seen = set(before_ids or [])
        last_check = None
        start = time.time()
        while time.time() - start < timeout:
            params = {"email": account.email}
            if last_check:
                params["lastCheck"] = last_check
            try:
                r = requests.get(f"{self.api}/poll", params=params, timeout=10)
                data = r.json()
                last_check = data.get("lastChecked")
                if data.get("count", 0) > 0:
                    r2 = requests.get(f"{self.api}/emails", params={"email": account.email}, timeout=10)
                    for mail in r2.json().get("emails", []):
                        mid = str(mail.get("id", ""))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        text = str(mail.get("preview", "")) + " " + str(mail.get("content", ""))
                        link = _extract_verification_link(text, keyword)
                        if link:
                            return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class TempMailLolMailbox(BaseMailbox):
    """tempmail.lol 免费临时邮箱（无需注册，自动生成）"""

    def __init__(self, proxy: str = None):
        self.api = "https://api.tempmail.lol/v2"
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self._token = None
        self._email = None

    def get_email(self) -> MailboxAccount:
        import requests
        r = requests.post(f"{self.api}/inbox/create",
            json={},
            proxies=self.proxy, timeout=15)
        data = r.json()
        self._email = data.get("address") or data.get("email", "")
        self._token = data.get("token", "")
        return MailboxAccount(
            email=self._email,
            account_id=self._token,
            extra={
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "tempmail_lol",
                    "resource_type": "mailbox",
                    "resource_identifier": self._token,
                    "handle": self._email,
                    "display_name": self._email,
                    "metadata": {
                        "email": self._email,
                        "token": self._token,
                    },
                },
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        import requests
        try:
            r = requests.get(f"{self.api}/inbox",
                params={"token": account.account_id},
                proxies=self.proxy, timeout=10)
            return {str(m["id"]) for m in r.json().get("emails", [])}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re, time, requests
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"{self.api}/inbox",
                    params={"token": account.account_id},
                    proxies=self.proxy, timeout=10)
                for mail in sorted(r.json().get("emails", []), key=lambda x: x.get("date", 0), reverse=True):
                    mid = str(mail.get("id", ""))
                    if mid in seen:
                        continue
                    seen.add(mid)
                    text = mail.get("subject", "") + " " + mail.get("body", "") + " " + mail.get("html", "")
                    if keyword and keyword.lower() not in text.lower():
                        continue
                    m = re.search(code_pattern or r'(?<!#)(?<!\d)(\d{6})(?!\d)', text)
                    if m:
                        return m.group(1) if m.groups() else m.group(0)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time, requests
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"{self.api}/inbox",
                    params={"token": account.account_id},
                    proxies=self.proxy, timeout=10)
                for mail in sorted(r.json().get("emails", []), key=lambda x: x.get("date", 0), reverse=True):
                    mid = str(mail.get("id", ""))
                    if mid in seen:
                        continue
                    seen.add(mid)
                    text = str(mail.get("subject", "")) + " " + str(mail.get("body", "")) + " " + str(mail.get("html", ""))
                    link = _extract_verification_link(text, keyword)
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class DuckMailMailbox(BaseMailbox):
    """DuckMail 自动生成邮箱（随机创建账号）"""

    def __init__(self, api_url: str = "https://www.duckmail.sbs",
                 provider_url: str = "https://api.duckmail.sbs",
                 bearer: str = "kevin273945",
                 proxy: str = None):
        self.api = api_url.rstrip("/")
        self.provider_url = provider_url
        self.bearer = bearer
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self._token = None
        self._address = None

    def _common_headers(self) -> dict:
        return {
            "authorization": f"Bearer {self.bearer}",
            "content-type": "application/json",
            "x-api-provider-base-url": self.provider_url,
        }

    def get_email(self) -> MailboxAccount:
        import requests, random, string
        username = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        password = "Test" + "".join(random.choices(string.digits, k=8)) + "!"
        domain = self.provider_url.replace("https://api.", "").replace("https://", "")
        address = f"{username}@{domain}"
        # 创建账号
        r = requests.post(f"{self.api}/api/mail?endpoint=%2Faccounts",
            json={"address": address, "password": password},
            headers=self._common_headers(), proxies=self.proxy, timeout=15, verify=False)
        data = r.json()
        self._address = data.get("address", address)
        # 登录获取 token
        r2 = requests.post(f"{self.api}/api/mail?endpoint=%2Ftoken",
            json={"address": self._address, "password": password},
            headers=self._common_headers(), proxies=self.proxy, timeout=15, verify=False)
        self._token = r2.json().get("token", "")
        return MailboxAccount(
            email=self._address,
            account_id=self._token,
            extra={
                "provider_account": {
                    "provider_type": "mailbox",
                    "provider_name": "duckmail",
                    "login_identifier": self._address,
                    "display_name": self._address,
                    "credentials": {
                        "address": self._address,
                        "password": password,
                        "token": self._token,
                    },
                    "metadata": {
                        "provider_url": self.provider_url,
                        "api_url": self.api,
                    },
                },
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "duckmail",
                    "resource_type": "mailbox",
                    "resource_identifier": self._token,
                    "handle": self._address,
                    "display_name": self._address,
                    "metadata": {
                        "email": self._address,
                        "provider_url": self.provider_url,
                    },
                },
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        import requests
        try:
            r = requests.get(f"{self.api}/api/mail?endpoint=%2Fmessages%3Fpage%3D1",
                headers={"authorization": f"Bearer {account.account_id}",
                         "x-api-provider-base-url": self.provider_url},
                proxies=self.proxy, timeout=10, verify=False)
            return {str(m["id"]) for m in r.json().get("hydra:member", [])}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re, time, requests
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"{self.api}/api/mail?endpoint=%2Fmessages%3Fpage%3D1",
                    headers={"authorization": f"Bearer {account.account_id}",
                             "x-api-provider-base-url": self.provider_url},
                    proxies=self.proxy, timeout=10, verify=False)
                msgs = r.json().get("hydra:member", [])
                for msg in msgs:
                    mid = str(msg.get("id") or msg.get("msgid") or "")
                    if mid in seen: continue
                    seen.add(mid)
                    # 请求邮件详情获取完整 text
                    try:
                        r2 = requests.get(f"{self.api}/api/mail?endpoint=%2Fmessages%2F{mid}",
                            headers={"authorization": f"Bearer {account.account_id}",
                                     "x-api-provider-base-url": self.provider_url},
                            proxies=self.proxy, timeout=10, verify=False)
                        detail = r2.json()
                        body = str(detail.get("text") or "") + " " + str(detail.get("subject") or "")
                    except Exception:
                        body = str(msg.get("subject") or "")
                    body = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', body)
                    m = re.search(r"(?<!#)(?<!\d)(\d{6})(?!\d)", body)
                    if m: return m.group(1)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time, requests
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"{self.api}/api/mail?endpoint=%2Fmessages%3Fpage%3D1",
                    headers={"authorization": f"Bearer {account.account_id}",
                             "x-api-provider-base-url": self.provider_url},
                    proxies=self.proxy, timeout=10, verify=False)
                msgs = r.json().get("hydra:member", [])
                for msg in msgs:
                    mid = str(msg.get("id") or msg.get("msgid") or "")
                    if mid in seen:
                        continue
                    seen.add(mid)
                    try:
                        r2 = requests.get(f"{self.api}/api/mail?endpoint=%2Fmessages%2F{mid}",
                            headers={"authorization": f"Bearer {account.account_id}",
                                     "x-api-provider-base-url": self.provider_url},
                            proxies=self.proxy, timeout=10, verify=False)
                        detail = r2.json()
                        body = str(detail.get("text") or "") + " " + str(detail.get("html") or "") + " " + str(detail.get("subject") or "")
                    except Exception:
                        body = str(msg.get("subject") or "")
                    link = _extract_verification_link(body, keyword)
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class CFWorkerMailbox(BaseMailbox):
    """Cloudflare Worker 自建临时邮箱服务"""

    def __init__(self, api_url: str, admin_token: str = "", domain: str = "",
                 fingerprint: str = "", proxy: str = None):
        self.api = api_url.rstrip("/")
        self.admin_token = admin_token
        self.domain = domain
        self.fingerprint = fingerprint
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self._token = None

    def _headers(self) -> dict:
        h = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "x-admin-auth": self.admin_token,
        }
        if self.fingerprint:
            h["x-fingerprint"] = self.fingerprint
        return h

    def get_email(self) -> MailboxAccount:
        import requests, random, string
        name = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        payload = {"enablePrefix": True, "name": name}
        if self.domain:
            payload["domain"] = self.domain
        r = requests.post(f"{self.api}/admin/new_address",
            json=payload, headers=self._headers(),
            proxies=self.proxy, timeout=15)
        print(f"[CFWorker] new_address status={r.status_code} resp={r.text[:200]}")
        data = r.json()
        email = data.get("email", data.get("address", ""))
        token = data.get("token", data.get("jwt", ""))
        self._token = token
        print(f"[CFWorker] 生成邮箱: {email} token={token[:40] if token else 'NONE'}...")
        return MailboxAccount(
            email=email,
            account_id=token,
            extra={
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "cfworker",
                    "resource_type": "mailbox",
                    "resource_identifier": token or email,
                    "handle": email,
                    "display_name": email,
                    "metadata": {
                        "email": email,
                        "token": token,
                        "api_url": self.api,
                        "domain": self.domain,
                    },
                },
            },
        )

    def _get_mails(self, email: str) -> list:
        import requests
        r = requests.get(f"{self.api}/admin/mails",
            params={"limit": 20, "offset": 0, "address": email},
            headers=self._headers(), proxies=self.proxy, timeout=10)
        data = r.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            mails = self._get_mails(account.email)
            return {str(m.get("id", "")) for m in mails}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re, time
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                mails = self._get_mails(account.email)
                for mail in sorted(mails, key=lambda x: x.get("id", 0), reverse=True):
                    mid = str(mail.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    raw = str(mail.get("raw", ""))
                    # 1. 优先匹配 <span>XXXXXX</span> （Trae 邮件格式）
                    code_m = re.search(r'<span[^>]*>\s*(\d{6})\s*</span>', raw)
                    if code_m:
                        return code_m.group(1)
                    # 2. 跳过 MIME header，只搜 body 部分，避免匹配时间戳
                    body_start = raw.find('\r\n\r\n')
                    search_text = raw[body_start:] if body_start != -1 else raw
                    search_text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', search_text)
                    # 排除时间戳模式 m=+XXXXXX. 和 t=XXXXXXXXXX
                    search_text = re.sub(r'm=\+\d+\.\d+', '', search_text)
                    search_text = re.sub(r'\bt=\d+\b', '', search_text)
                    m = re.search(code_pattern or r'(?<!#)(?<!\d)(\d{6})(?!\d)', search_text)
                    if m:
                        return m.group(1) if m.groups() else m.group(0)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                mails = self._get_mails(account.email)
                for mail in sorted(mails, key=lambda x: x.get("id", 0), reverse=True):
                    mid = str(mail.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    raw = str(mail.get("raw", ""))
                    link = _extract_verification_link(raw, keyword)
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class MoeMailMailbox(BaseMailbox):
    """MoeMail (sall.cc) 邮箱服务 - 自动注册账号并生成临时邮箱"""

    def __init__(
        self,
        api_url: str = "https://sall.cc",
        username: str = "",
        password: str = "",
        session_token: str = "",
        proxy: str = None,
    ):
        self.api = _normalize_api_base_url(api_url, default="https://sall.cc", label="MoeMail API URL")
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self._configured_username = str(username or "").strip()
        self._configured_password = str(password or "")
        self._configured_session_token = str(session_token or "").strip()
        self._session_token = self._configured_session_token or None
        self._email = None
        self._session = None
        self._username = self._configured_username
        self._password = self._configured_password

    def _new_session(self):
        import requests

        s = requests.Session()
        s.proxies = self.proxy
        s.verify = False
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        s.headers.update({"user-agent": ua, "origin": self.api, "referer": f"{self.api}/zh-CN/login"})
        return s

    def _extract_session_token(self, session) -> str:
        for cookie in session.cookies:
            if "session-token" in cookie.name:
                return cookie.value
        return ""

    def _apply_session_token(self, session, token: str) -> None:
        domain = urlparse(self.api).hostname or ""
        cookie_names = [
            "__Secure-authjs.session-token",
            "authjs.session-token",
            "__Secure-next-auth.session-token",
            "next-auth.session-token",
        ]
        for name in cookie_names:
            session.cookies.set(name, token, domain=domain, path="/")
            session.cookies.set(name, token, path="/")

    def _login_with_existing_account(self) -> str:
        s = self._new_session()

        if self._configured_session_token:
            self._apply_session_token(s, self._configured_session_token)
            self._session = s
            self._session_token = self._configured_session_token
            print("[MoeMail] 使用已提供的 session-token")
            return self._configured_session_token

        if not (self._configured_username and self._configured_password):
            raise RuntimeError("MoeMail 未配置可复用账号，请提供用户名密码或 session-token")

        csrf_r = s.get(f"{self.api}/api/auth/csrf", timeout=10)
        csrf = csrf_r.json().get("csrfToken", "")
        login_resp = s.post(
            f"{self.api}/api/auth/callback/credentials",
            headers={"content-type": "application/x-www-form-urlencoded"},
            data=urlencode({
                "username": self._configured_username,
                "password": self._configured_password,
                "csrfToken": csrf,
                "redirect": "false",
                "callbackUrl": self.api,
            }),
            allow_redirects=True,
            timeout=15,
        )
        self._session = s
        self._username = self._configured_username
        self._password = self._configured_password
        token = self._extract_session_token(s)
        if token:
            self._session_token = token
            print("[MoeMail] 使用手动注册账号登录成功")
            return token
        raise RuntimeError(
            f"MoeMail 登录失败: 已提供用户名密码，但未获取到 session-token (HTTP {login_resp.status_code})"
        )

    def _ensure_session(self) -> str:
        if self._session_token and self._session is not None:
            return self._session_token
        if self._configured_session_token or self._configured_username:
            return self._login_with_existing_account()
        return self._register_and_login()

    def _register_and_login(self) -> str:
        import random, string

        s = self._new_session()
        # 注册
        username = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        password = "Test" + "".join(random.choices(string.digits, k=8)) + "!"
        self._username = username
        self._password = password
        print(f"[MoeMail] 注册账号: {username} / {password}")
        r_reg = s.post(f"{self.api}/api/auth/register",
            json={"username": username, "password": password, "turnstileToken": ""},
            timeout=15)
        print(f"[MoeMail] 注册结果: {r_reg.status_code} {r_reg.text[:80]}")
        if r_reg.status_code >= 400:
            try:
                register_error = r_reg.json().get("error") or r_reg.text
            except Exception:
                register_error = r_reg.text
            raise RuntimeError(f"MoeMail 注册失败: {str(register_error).strip() or f'HTTP {r_reg.status_code}'}")
        # 获取 CSRF
        csrf_r = s.get(f"{self.api}/api/auth/csrf", timeout=10)
        csrf = csrf_r.json().get("csrfToken", "")
        # 登录
        login_resp = s.post(f"{self.api}/api/auth/callback/credentials",
            headers={"content-type": "application/x-www-form-urlencoded"},
            data=urlencode({
                "username": username,
                "password": password,
                "csrfToken": csrf,
                "redirect": "false",
                "callbackUrl": self.api,
            }),
            allow_redirects=True, timeout=15)
        self._session = s
        token = self._extract_session_token(s)
        if token:
            self._session_token = token
            print(f"[MoeMail] 登录成功")
            return token
        print(f"[MoeMail] 登录失败，cookies: {[c.name for c in s.cookies]}")
        raise RuntimeError(
            f"MoeMail 登录失败: 未获取到 session-token (HTTP {login_resp.status_code})"
        )

    # 优先用这些域名（信誉较好，不易被 AWS/Google 等拒绝）
    _PREFERRED_DOMAINS = ("sall.cc", "cnmlgb.de", "zhooo.org", "coolkid.icu")

    def get_email(self) -> MailboxAccount:
        self._session_token = self._configured_session_token or None
        self._session = None
        self._ensure_session()
        import random, string
        name = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        # 获取可用域名列表，优先选信誉好的域名，避免被 AWS 等平台拒绝
        domain = "sall.cc"
        try:
            cfg_r = self._session.get(f"{self.api}/api/config", timeout=10)
            all_domains = [d.strip() for d in cfg_r.json().get("emailDomains", "sall.cc").split(",") if d.strip()]
            if all_domains:
                # 从可用域名中筛选优先域名，按 _PREFERRED_DOMAINS 顺序选择
                preferred = [d for d in self._PREFERRED_DOMAINS if d in all_domains]
                if preferred:
                    domain = random.choice(preferred)
                else:
                    # 无优先域名可用，从剩余中随机选
                    domain = random.choice(all_domains)
        except Exception:
            pass
        r = self._session.post(f"{self.api}/api/emails/generate",
            json={"name": name, "domain": domain, "expiryTime": 86400000},
            timeout=15)
        data = r.json()
        self._email = data.get("email", data.get("address", ""))
        email_id = data.get("id", "")
        print(f"[MoeMail] 生成邮箱: {self._email} id={email_id} domain={domain} status={r.status_code}")
        if not email_id:
            print(f"[MoeMail] 生成失败: {data}")
            generate_error = data.get("error") or data.get("message") or r.text
            raise RuntimeError(f"MoeMail 生成邮箱失败: {str(generate_error).strip() or f'HTTP {r.status_code}'}")
        if not self._email:
            raise RuntimeError("MoeMail 生成邮箱失败: 返回结果缺少 email")
        self._email_count = getattr(self, '_email_count', 0) + 1
        return MailboxAccount(
            email=self._email,
            account_id=str(email_id),
            extra={
                "provider_account": {
                    "provider_type": "mailbox",
                    "provider_name": "moemail",
                    "login_identifier": getattr(self, "_username", ""),
                    "display_name": getattr(self, "_username", "") or self._email,
                    "credentials": {
                        "username": getattr(self, "_username", ""),
                        "password": getattr(self, "_password", ""),
                        "session_token": self._session_token,
                    },
                    "metadata": {
                        "api_url": self.api,
                        "email": self._email,
                    },
                },
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "moemail",
                    "resource_type": "mailbox",
                    "resource_identifier": str(email_id),
                    "handle": self._email,
                    "display_name": self._email,
                    "metadata": {
                        "email": self._email,
                        "api_url": self.api,
                    },
                },
            },
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            r = self._session.get(f"{self.api}/api/emails/{account.account_id}", timeout=10)
            return {str(m.get("id", "")) for m in r.json().get("messages", [])}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None,
                      code_pattern: str = None) -> str:
        import re, time
        seen = set(before_ids or [])
        start = time.time()
        pattern = re.compile(code_pattern) if code_pattern else None
        while time.time() - start < timeout:
            try:
                r = self._session.get(f"{self.api}/api/emails/{account.account_id}",
                    timeout=10)
                msgs = r.json().get("messages", [])
                for msg in msgs:
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen: continue
                    seen.add(mid)
                    body = str(msg.get("content") or msg.get("text") or msg.get("body") or msg.get("html") or "") + " " + str(msg.get("subject") or "")
                    body = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', body)
                    if pattern:
                        m = pattern.search(body)
                    else:
                        m = re.search(code_pattern or r'(?<!#)(?<!\d)(\d{6})(?!\d)', body)
                    if m: return m.group(1) if m.groups() else m.group(0) if code_pattern else m.group(1)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = self._session.get(f"{self.api}/api/emails/{account.account_id}",
                    timeout=10)
                msgs = r.json().get("messages", [])
                for msg in msgs:
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    body = (
                        str(msg.get("content") or "") + " " +
                        str(msg.get("text") or "") + " " +
                        str(msg.get("body") or "") + " " +
                        str(msg.get("html") or "") + " " +
                        str(msg.get("subject") or "")
                    )
                    link = _extract_verification_link(body, keyword)
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")


class FreemailMailbox(BaseMailbox):
    """
    Freemail 自建邮箱服务（基于 Cloudflare Worker）
    项目: https://github.com/idinging/freemail
    支持管理员令牌或账号密码两种认证方式
    """

    def __init__(self, api_url: str, admin_token: str = "",
                 username: str = "", password: str = "",
                 proxy: str = None):
        self.api = api_url.rstrip("/")
        self.admin_token = admin_token
        self.username = username
        self.password = password
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self._session = None
        self._email = None

    def _get_session(self):
        import requests
        s = requests.Session()
        s.proxies = self.proxy
        if self.admin_token:
            s.headers.update({"Authorization": f"Bearer {self.admin_token}"})
        elif self.username and self.password:
            s.post(f"{self.api}/api/login",
                json={"username": self.username, "password": self.password},
                timeout=15)
        self._session = s
        return s

    def get_email(self) -> MailboxAccount:
        if not self._session:
            self._get_session()
        import requests
        r = self._session.get(f"{self.api}/api/generate", timeout=15)
        data = r.json()
        email = data.get("email", "")
        self._email = email
        print(f"[Freemail] 生成邮箱: {email}")
        provider_account = {
            "provider_type": "mailbox",
            "provider_name": "freemail",
            "login_identifier": self.username or email,
            "display_name": self.username or email,
            "credentials": {},
            "metadata": {
                "api_url": self.api,
                "auth_mode": "admin_token" if self.admin_token else "username_password",
            },
        }
        if self.admin_token:
            provider_account["credentials"]["admin_token"] = self.admin_token
        if self.username:
            provider_account["credentials"]["username"] = self.username
        if self.password:
            provider_account["credentials"]["password"] = self.password
        return MailboxAccount(
            email=email,
            account_id=email,
            extra={
                "provider_account": provider_account,
                "provider_resource": {
                    "provider_type": "mailbox",
                    "provider_name": "freemail",
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

    def get_current_ids(self, account: MailboxAccount) -> set:
        try:
            r = self._session.get(f"{self.api}/api/emails",
                params={"mailbox": account.email, "limit": 50}, timeout=10)
            return {str(m["id"]) for m in r.json() if "id" in m}
        except Exception:
            return set()

    def wait_for_code(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None, code_pattern: str = None) -> str:
        import re, time
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = self._session.get(f"{self.api}/api/emails",
                    params={"mailbox": account.email, "limit": 20}, timeout=10)
                for msg in r.json():
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen: continue
                    seen.add(mid)
                    # 直接用 verification_code 字段
                    code = str(msg.get("verification_code") or "")
                    if code and code != "None":
                        return code
                    # 兜底：从 preview 提取
                    text = str(msg.get("preview", "")) + " " + str(msg.get("subject", ""))
                    m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
                    if m: return m.group(1)
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def wait_for_link(self, account: MailboxAccount, keyword: str = "",
                      timeout: int = 120, before_ids: set = None) -> str:
        import time
        seen = set(before_ids or [])
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = self._session.get(f"{self.api}/api/emails",
                    params={"mailbox": account.email, "limit": 20}, timeout=10)
                for msg in r.json():
                    mid = str(msg.get("id", ""))
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    text = " ".join(
                        str(msg.get(key, ""))
                        for key in ("preview", "subject", "html", "text", "content", "body")
                    )
                    link = _extract_verification_link(text, keyword)
                    if link:
                        return link
            except Exception:
                pass
            time.sleep(3)
        raise TimeoutError(f"等待验证链接超时 ({timeout}s)")
