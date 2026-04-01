"""
注册流程引擎
从 main.py 中提取并重构的注册流程
"""

import re
import json
import time
import logging
import secrets
import string
from typing import Optional, Dict, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from .oauth import OAuthManager, OAuthStart
from .http_client import OpenAIHTTPClient, HTTPClientError

# from ..services import EmailServiceFactory, BaseEmailService, EmailServiceType  # removed: external dep
# from ..database import crud  # removed: external dep
# from ..database.session import get_db  # removed: external dep
from .constants import (
    OPENAI_API_ENDPOINTS,
    OPENAI_PAGE_TYPES,
    generate_random_user_info,
    OTP_CODE_PATTERN,
    DEFAULT_PASSWORD_LENGTH,
    PASSWORD_CHARSET,
    AccountStatus,
    TaskStatus,
)
# from ..config.settings import get_settings  # removed: external dep


logger = logging.getLogger(__name__)


@dataclass
class RegistrationResult:
    """注册结果"""

    success: bool
    email: str = ""
    password: str = ""  # 注册密码
    account_id: str = ""
    workspace_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    id_token: str = ""
    session_token: str = ""  # 会话令牌
    error_message: str = ""
    logs: list = None
    metadata: dict = None
    source: str = "register"  # 'register' 或 'login'，区分账号来源

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "email": self.email,
            "password": self.password,
            "account_id": self.account_id,
            "workspace_id": self.workspace_id,
            "access_token": self.access_token[:20] + "..." if self.access_token else "",
            "refresh_token": self.refresh_token[:20] + "..."
            if self.refresh_token
            else "",
            "id_token": self.id_token[:20] + "..." if self.id_token else "",
            "session_token": self.session_token[:20] + "..."
            if self.session_token
            else "",
            "error_message": self.error_message,
            "logs": self.logs or [],
            "metadata": self.metadata or {},
            "source": self.source,
        }


@dataclass
class SignupFormResult:
    """提交注册表单的结果"""

    success: bool
    page_type: str = ""  # 响应中的 page.type 字段
    is_existing_account: bool = False  # 是否为已注册账号
    response_data: Dict[str, Any] = None  # 完整的响应数据
    error_message: str = ""


class RegistrationEngine:
    """
    注册引擎
    负责协调邮箱服务、OAuth 流程和 OpenAI API 调用
    """

    def __init__(
        self,
        email_service: Any,
        proxy_url: Optional[str] = None,
        callback_logger: Optional[Callable[[str], None]] = None,
        task_uuid: Optional[str] = None,
    ):
        """
        初始化注册引擎

        Args:
            email_service: 邮箱服务实例
            proxy_url: 代理 URL
            callback_logger: 日志回调函数
            task_uuid: 任务 UUID（用于数据库记录）
        """
        self.email_service = email_service
        self.proxy_url = proxy_url
        self.callback_logger = callback_logger or (lambda msg: logger.info(msg))
        self.task_uuid = task_uuid

        # 创建 HTTP 客户端
        self.http_client = OpenAIHTTPClient(proxy_url=proxy_url)

        # 创建 OAuth 管理器
        from .constants import (
            OAUTH_CLIENT_ID,
            OAUTH_AUTH_URL,
            OAUTH_TOKEN_URL,
            OAUTH_REDIRECT_URI,
            OAUTH_SCOPE,
        )

        self.oauth_manager = OAuthManager(
            client_id=OAUTH_CLIENT_ID,
            auth_url=OAUTH_AUTH_URL,
            token_url=OAUTH_TOKEN_URL,
            redirect_uri=OAUTH_REDIRECT_URI,
            scope=OAUTH_SCOPE,
            proxy_url=proxy_url,  # 传递代理配置
        )

        # 状态变量
        self.email: Optional[str] = None
        self.password: Optional[str] = None  # 注册密码
        self.email_info: Optional[Dict[str, Any]] = None
        self.oauth_start: Optional[OAuthStart] = None
        self.session: Optional[cffi_requests.Session] = None
        self.session_token: Optional[str] = None  # 会话令牌
        self.logs: list = []
        self._otp_sent_at: Optional[float] = None  # OTP 发送时间戳
        self._is_existing_account: bool = False  # 是否为已注册账号（用于自动登录）
        self._create_account_continue_url: str = ""
        self._create_account_page_type: str = ""
        self._create_account_continue_kind: str = ""

    def _log(self, message: str, level: str = "info"):
        """记录日志"""
        timestamp = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"

        # 添加到日志列表
        self.logs.append(log_message)

        # 调用回调函数
        if self.callback_logger:
            self.callback_logger(message)

        # 记录到数据库（如果有关联任务）
        if self.task_uuid:
            try:
                with get_db() as db:
                    crud.append_task_log(db, self.task_uuid, message)
            except Exception as e:
                logger.warning(f"记录任务日志失败: {e}")

        # 根据级别记录到日志系统
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def _generate_password(self, length: int = DEFAULT_PASSWORD_LENGTH) -> str:
        """生成随机密码"""
        return "".join(secrets.choice(PASSWORD_CHARSET) for _ in range(length))

    def _check_ip_location(self) -> Tuple[bool, Optional[str]]:
        """检查 IP 地理位置"""
        try:
            return self.http_client.check_ip_location()
        except Exception as e:
            self._log(f"检查 IP 地理位置失败: {e}", "error")
            return False, None

    def _create_email(self) -> bool:
        """创建邮箱"""
        try:
            self._log(f"正在创建 {self.email_service.service_type.value} 邮箱...")
            self.email_info = self.email_service.create_email()

            if not self.email_info or "email" not in self.email_info:
                self._log("创建邮箱失败: 返回信息不完整", "error")
                return False

            self.email = self.email_info["email"]
            self._log(f"成功创建邮箱: {self.email}")
            return True

        except Exception as e:
            self._log(f"创建邮箱失败: {e}", "error")
            return False

    def _start_oauth(self) -> bool:
        """开始 OAuth 流程"""
        try:
            self._log("开始 OAuth 授权流程...")
            self.oauth_start = self.oauth_manager.start_oauth()
            self._log(f"OAuth URL 已生成: {self.oauth_start.auth_url[:80]}...")
            return True
        except Exception as e:
            self._log(f"生成 OAuth URL 失败: {e}", "error")
            return False

    def _init_session(self) -> bool:
        """初始化会话"""
        try:
            self.session = self.http_client.session
            return True
        except Exception as e:
            self._log(f"初始化会话失败: {e}", "error")
            return False

    def _get_device_id(self) -> Optional[str]:
        """获取 Device ID"""
        try:
            if not self.oauth_start:
                return None

            response = self.session.get(self.oauth_start.auth_url, timeout=15)
            did = self.session.cookies.get("oai-did")
            self._log(f"Device ID: {did}")
            return did

        except Exception as e:
            self._log(f"获取 Device ID 失败: {e}", "error")
            return None

    def _check_sentinel(
        self, did: str, flow: str = "authorize_continue"
    ) -> Optional[Dict[str, str]]:
        """
        检查 Sentinel 拦截

        Args:
            did: Device ID
            flow: Sentinel Flow

        Returns:
            包含 token 和 so-token 的字典，或 None
        """
        try:
            self._log(f"正在进行 Sentinel 校验 (flow: {flow})...")
            sen_req_body = f'{{"p":"","id":"{did}","flow":"{flow}"}}'

            response = self.session.post(
                OPENAI_API_ENDPOINTS["sentinel"],
                headers={
                    "origin": "https://sentinel.openai.com",
                    "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6",
                    "content-type": "text/plain;charset=UTF-8",
                },
                data=sen_req_body,
            )

            if response.status_code == 200:
                res_data = response.json()
                sen_token = res_data.get("token")
                self._log(f"Sentinel token 获取成功")

                # 在某些流程中，我们需要获取 so-token
                # 目前根据抓包分析，so 值在不同的 flow 中可能保持一致或有一定的加密逻辑
                # 暂时使用抓包中提取的特征值进行模拟
                so_val = "QxcZDxYLAwwCGnlke297amxvemoMfG15X359SV9ofHRvBRoUFx0BFgECDAIae2RNBRoUFxcAFg8EDAIae3QTBRoUFxsBFgAEDAIae3QTBRoUFxwMFgEADAIae11dYHt5Wmx5UFt0bXlffX1/S3R8QlkFGhQXGAwWCwAMAhp7dBMFGhQXHBYLDxcUGnt5CBMaFBoMHRYJDBcUGnt5CBMaFBoFAAAJGg8Me2lxb2ppX3J3bE92fHRdfX9PCBMaFBoMAAAaAhdtaXFicX9fcnp3WXd7T0Zjf2kFCAwUGg8EAA4AGg8Me09tUW9pX293Vlt6eWRrdX5PcG95eQhWDBQaDQMADAAaDwx8aQUIDBQaDwcAAAEaDwx7X31QDBQaDgEADAkaDwx5aWFUaF9fenFsW3p5ZGt1f2kNYXx5CAgMFBoJAQAPGgIXak8FBRcCGg8LGxYMGgIXbXpLb3RvfXN5XU1ye3lGbH95CHRqaWEFFwIaDwwbGA0aAhdqakthdH8Md3p3SXN8T15gcGlXfmpPWwUXAhoJCBsbGgIadmxLWntSRWh6UFZke09fd2ZpT2h0b1thGkg="

                return {"token": sen_token, "so": so_val}
            else:
                self._log(f"Sentinel 检查失败: {response.status_code}", "warning")
                return None

        except Exception as e:
            self._log(f"Sentinel 检查异常: {e}", "warning")
            return None

    def _submit_signup_form(
        self, did: str, sen_data: Optional[Dict[str, str]]
    ) -> SignupFormResult:
        """
        提交注册表单

        Returns:
            SignupFormResult: 提交结果，包含账号状态判断
        """
        try:
            signup_body = f'{{"username":{{"value":"{self.email}","kind":"email"}},"screen_hint":"signup"}}'

            headers = {
                "referer": "https://auth.openai.com/create-account",
                "accept": "application/json",
                "content-type": "application/json",
            }

            if sen_data:
                sen_token = sen_data.get("token")
                sentinel = f'{{"p": "", "t": "", "c": "{sen_token}", "id": "{did}", "flow": "authorize_continue"}}'
                headers["openai-sentinel-token"] = sentinel

            response = self.session.post(
                OPENAI_API_ENDPOINTS["signup"],
                headers=headers,
                data=signup_body,
            )

            self._log(f"提交注册表单状态: {response.status_code}")

            if response.status_code != 200:
                return SignupFormResult(
                    success=False,
                    error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                )

            # 解析响应判断账号状态
            try:
                response_data = response.json()
                page_type = response_data.get("page", {}).get("type", "")
                self._log(f"响应页面类型: {page_type}")

                # 判断是否为已注册账号
                is_existing = page_type == OPENAI_PAGE_TYPES["EMAIL_OTP_VERIFICATION"]

                if is_existing:
                    self._log(f"检测到已注册账号，将自动切换到登录流程")
                    self._is_existing_account = True

                return SignupFormResult(
                    success=True,
                    page_type=page_type,
                    is_existing_account=is_existing,
                    response_data=response_data,
                )

            except Exception as parse_error:
                self._log(f"解析响应失败: {parse_error}", "warning")
                # 无法解析，默认成功
                return SignupFormResult(success=True)

        except Exception as e:
            self._log(f"提交注册表单失败: {e}", "error")
            return SignupFormResult(success=False, error_message=str(e))

    def _register_password(self) -> Tuple[bool, Optional[str]]:
        """注册密码"""
        try:
            # 生成密码
            password = self._generate_password()
            self.password = password  # 保存密码到实例变量
            self._log(f"生成密码: {password}")

            # 提交密码注册
            register_body = json.dumps({"password": password, "username": self.email})

            response = self.session.post(
                OPENAI_API_ENDPOINTS["register"],
                headers={
                    "referer": "https://auth.openai.com/create-account/password",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                data=register_body,
            )

            self._log(f"提交密码状态: {response.status_code}")

            if response.status_code != 200:
                error_text = response.text[:500]
                self._log(f"密码注册失败: {error_text}", "warning")

                # 解析错误信息，判断是否是邮箱已注册
                try:
                    error_json = response.json()
                    error_msg = error_json.get("error", {}).get("message", "")
                    error_code = error_json.get("error", {}).get("code", "")

                    # 检测邮箱已注册的情况
                    if (
                        "already" in error_msg.lower()
                        or "exists" in error_msg.lower()
                        or error_code == "user_exists"
                    ):
                        self._log(f"邮箱 {self.email} 可能已在 OpenAI 注册过", "error")
                        # 标记此邮箱为已注册状态
                        self._mark_email_as_registered()
                except Exception:
                    pass

                return False, None

            return True, password

        except Exception as e:
            self._log(f"密码注册失败: {e}", "error")
            return False, None

    def _mark_email_as_registered(self):
        """标记邮箱为已注册状态（用于防止重复尝试）"""
        try:
            with get_db() as db:
                # 检查是否已存在该邮箱的记录
                existing = crud.get_account_by_email(db, self.email)
                if not existing:
                    # 创建一个失败记录，标记该邮箱已注册过
                    crud.create_account(
                        db,
                        email=self.email,
                        password="",  # 空密码表示未成功注册
                        email_service=self.email_service.service_type.value,
                        email_service_id=self.email_info.get("service_id")
                        if self.email_info
                        else None,
                        status="failed",
                        extra_data={
                            "register_failed_reason": "email_already_registered_on_openai"
                        },
                    )
                    self._log(f"已在数据库中标记邮箱 {self.email} 为已注册状态")
        except Exception as e:
            logger.warning(f"标记邮箱状态失败: {e}")

    def _send_verification_code(self) -> bool:
        """发送验证码"""
        try:
            # 记录发送时间戳
            self._otp_sent_at = time.time()

            response = self.session.get(
                OPENAI_API_ENDPOINTS["send_otp"],
                headers={
                    "referer": "https://auth.openai.com/create-account/password",
                    "accept": "application/json",
                },
            )

            self._log(f"验证码发送状态: {response.status_code}")
            return response.status_code == 200

        except Exception as e:
            self._log(f"发送验证码失败: {e}", "error")
            return False

    def _get_verification_code(self) -> Optional[str]:
        """获取验证码"""
        try:
            self._log(f"正在等待邮箱 {self.email} 的验证码...")

            email_id = self.email_info.get("service_id") if self.email_info else None
            code = self.email_service.get_verification_code(
                email=self.email,
                email_id=email_id,
                timeout=120,
                pattern=OTP_CODE_PATTERN,
                otp_sent_at=self._otp_sent_at,
            )

            if code:
                self._log(f"成功获取验证码: {code}")
                return code
            else:
                self._log("等待验证码超时", "error")
                return None

        except Exception as e:
            self._log(f"获取验证码失败: {e}", "error")
            return None

    def _validate_verification_code(self, code: str) -> bool:
        """验证验证码"""
        try:
            code_body = f'{{"code":"{code}"}}'

            response = self.session.post(
                OPENAI_API_ENDPOINTS["validate_otp"],
                headers={
                    "referer": "https://auth.openai.com/email-verification",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                data=code_body,
            )

            self._log(f"验证码校验状态: {response.status_code}")
            return response.status_code == 200

        except Exception as e:
            self._log(f"验证验证码失败: {e}", "error")
            return False

    def _create_user_account(self) -> bool:
        """创建用户账户"""
        try:
            # 0. 获取 Device ID（如果之前由于某种原因没有获取到）
            did = self.session.cookies.get("oai-did")
            if not did:
                self._log(
                    "未检测到 oai-did cookie，尝试手动获取 Device ID...", "warning"
                )
                did = self._get_device_id()
                if not did:
                    self._log(
                        "获取 Device ID 失败，尝试继续发起的 create_account 可能会被拦截",
                        "warning",
                    )

            # 1. 在创建账户前执行 Sentinel 校验 (flow: oauth_create_account)
            sen_data = None
            if did:
                sen_data = self._check_sentinel(did, flow="oauth_create_account")

            # 2. 生成用户信息
            user_info = generate_random_user_info()
            self._log(
                f"生成用户信息: {user_info['name']}, 生日: {user_info['birthdate']}"
            )
            create_account_body = json.dumps(user_info)

            # 3. 构造请求头，包含抓包中要求的 Sentinel 令牌
            headers = {
                "referer": "https://auth.openai.com/about-you",
                "accept": "application/json",
                "content-type": "application/json",
            }

            if sen_data:
                # 使用 http_client 构建完整的 sentinel header（包含 PoW p 字段）
                sentinel_header = self.http_client.build_sentinel_header(
                    device_id=did,
                    flow="oauth_create_account",
                )
                headers["openai-sentinel-token"] = sentinel_header

                # 构造 openai-sentinel-so-token
                so_value = sen_data.get("so") or ""
                if so_value:
                    sentinel_so_token = {
                        "so": so_value,
                        "c": sen_data.get("token"),
                        "id": did,
                        "flow": "oauth_create_account",
                    }
                    headers["openai-sentinel-so-token"] = json.dumps(
                        sentinel_so_token, separators=(",", ":")
                    )

            response = self.session.post(
                OPENAI_API_ENDPOINTS["create_account"],
                headers=headers,
                data=create_account_body,
            )

            self._log(f"账户创建状态: {response.status_code}")

            if response.status_code != 200:
                self._log(f"账户创建失败: {response.text[:200]}", "warning")
                return False

            # 保存响应体，供后续提取 workspace_id
            try:
                self._create_account_response = response.json()
                self._log(
                    f"create_account 响应体 keys: {list(self._create_account_response.keys())}"
                )
                continue_url = str(
                    self._create_account_response.get("continue_url") or ""
                ).strip()
                page_info = self._create_account_response.get("page") or {}
                page_type = (
                    str(page_info.get("type") or "").strip()
                    if isinstance(page_info, dict)
                    else ""
                )
                continue_kind = "unknown"
                if continue_url:
                    if "callback/openai" in continue_url:
                        continue_kind = "callback_openai"
                    elif "add-phone" in continue_url:
                        continue_kind = "add_phone"
                    elif "workspace" in continue_url:
                        continue_kind = "workspace"
                    else:
                        import urllib.parse

                        continue_kind = (
                            f"other:{urllib.parse.urlparse(continue_url).path[:40]}"
                        )
                self._create_account_continue_url = continue_url
                self._create_account_page_type = page_type
                self._create_account_continue_kind = continue_kind
                self._log(
                    f"create_account 结果: page_type={page_type}, continue_kind={continue_kind}"
                )
                if continue_url:
                    self._log(f"continue_url from create_account: {continue_url[:120]}")
            except Exception:
                self._create_account_response = {}

            return True

        except Exception as e:
            self._log(f"创建账户失败: {e}", "error")
            return False

    def _get_workspace_id(self) -> Optional[str]:
        """从 oai-client-auth-session cookie 提取 workspace_id"""
        import base64
        import json as json_module

        try:
            auth_cookie = self.session.cookies.get("oai-client-auth-session") or ""
            if not auth_cookie:
                self._log("oai-client-auth-session cookie 不存在", "warning")
                return None

            segments = auth_cookie.split(".")
            for seg in segments:
                try:
                    pad = "=" * ((4 - (len(seg) % 4)) % 4)
                    decoded = base64.urlsafe_b64decode((seg + pad).encode("ascii"))
                    auth_json = json_module.loads(decoded.decode("utf-8"))
                    workspaces = auth_json.get("workspaces") or []
                    if workspaces:
                        wid = str((workspaces[0] or {}).get("id") or "").strip()
                        if wid:
                            self._log(f"Workspace ID (from cookie): {wid}")
                            return wid
                    ws = auth_json.get("workspace") or auth_json.get(
                        "default_workspace"
                    )
                    if ws:
                        wid = str(ws.get("id") or "").strip()
                        if wid:
                            self._log(f"Workspace ID (from cookie workspace): {wid}")
                            return wid
                except Exception:
                    continue
        except Exception as e:
            self._log(f"从 Cookie 提取 workspace_id 失败: {e}", "warning")

        self._log("Cookie 中未找到 workspace_id", "warning")
        return None

    def _select_workspace(self, workspace_id: str) -> Optional[str]:
        """选择 Workspace"""
        try:
            select_body = f'{{"workspace_id":"{workspace_id}"}}'

            response = self.session.post(
                OPENAI_API_ENDPOINTS["select_workspace"],
                headers={
                    "referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
                    "content-type": "application/json",
                },
                data=select_body,
            )

            if response.status_code != 200:
                self._log(f"选择 workspace 失败: {response.status_code}", "error")
                self._log(f"响应: {response.text[:200]}", "warning")
                return None

            continue_url = str(
                (response.json() or {}).get("continue_url") or ""
            ).strip()
            if not continue_url:
                self._log("workspace/select 响应里缺少 continue_url", "error")
                return None

            self._log(f"Continue URL: {continue_url[:100]}...")
            return continue_url

        except Exception as e:
            self._log(f"选择 Workspace 失败: {e}", "error")
            return None

    def _extract_token_from_cookie(self) -> Optional[Dict[str, Any]]:
        """从 oai-client-auth-session cookie 直接提取 access_token，跳过 OAuth callback。"""
        try:
            import base64, json as _json

            auth_cookie = self.session.cookies.get("oai-client-auth-session")
            if not auth_cookie:
                self._log("未找到 oai-client-auth-session cookie", "warning")
                return None

            segments = auth_cookie.split(".")
            if len(segments) < 2:
                self._log("Cookie 格式异常，无法提取 token", "warning")
                return None

            # 优先从 payload（segment[1]）提取
            for seg in (segments[1], segments[0]):
                try:
                    pad = "=" * ((4 - (len(seg) % 4)) % 4)
                    decoded = base64.urlsafe_b64decode((seg + pad).encode("ascii"))
                    data = _json.loads(decoded.decode("utf-8"))
                    access_token = str(data.get("access_token") or "").strip()
                    if access_token:
                        self._log("从 Cookie 直接提取到 access_token")
                        return {
                            "access_token": access_token,
                            "refresh_token": str(
                                data.get("refresh_token") or ""
                            ).strip(),
                            "id_token": str(data.get("id_token") or "").strip(),
                            "account_id": str(data.get("account_id") or "").strip(),
                            "email": self.email,
                        }
                except Exception:
                    continue

            self._log("Cookie 里未找到 access_token", "warning")
            return None
        except Exception as e:
            self._log(f"从 Cookie 提取 token 失败: {e}", "warning")
            return None

    def _follow_redirects(self, start_url: str) -> Optional[str]:
        """跟随重定向链，寻找回调 URL"""
        try:
            current_url = start_url
            max_redirects = 6

            for i in range(max_redirects):
                self._log(f"重定向 {i + 1}/{max_redirects}: {current_url[:100]}...")

                response = self.session.get(
                    current_url, allow_redirects=False, timeout=15
                )

                location = response.headers.get("Location") or ""

                # 如果不是重定向状态码，停止
                if response.status_code not in [301, 302, 303, 307, 308]:
                    self._log(f"非重定向状态码: {response.status_code}")
                    break

                if not location:
                    self._log("重定向响应缺少 Location 头")
                    break

                # 构建下一个 URL
                import urllib.parse

                next_url = urllib.parse.urljoin(current_url, location)

                # 检查是否包含回调参数
                if "code=" in next_url and "state=" in next_url:
                    self._log(f"找到回调 URL: {next_url[:100]}...")
                    return next_url

                current_url = next_url

            self._log("未能在重定向链中找到回调 URL", "error")
            return None

        except Exception as e:
            self._log(f"跟随重定向失败: {e}", "error")
            return None

    def _handle_oauth_callback(self, callback_url: str) -> Optional[Dict[str, Any]]:
        """处理 OAuth 回调"""
        try:
            if not self.oauth_start:
                self._log("OAuth 流程未初始化", "error")
                return None

            self._log("处理 OAuth 回调...")
            token_info = self.oauth_manager.handle_callback(
                callback_url=callback_url,
                expected_state=self.oauth_start.state,
                code_verifier=self.oauth_start.code_verifier,
            )

            self._log("OAuth 授权成功")
            return token_info

        except Exception as e:
            self._log(f"处理 OAuth 回调失败: {e}", "error")
            return None

    def _try_create_account_callback_session_token(
        self, continue_url: str
    ) -> Optional[Dict[str, Any]]:
        """从 create_account 的 continue_url 直接获取 session token（绕过 workspace 流程）"""
        if not self.session or not continue_url:
            return None

        import urllib.parse

        parsed = urllib.parse.urlparse(continue_url)
        if parsed.netloc != "chatgpt.com" or not parsed.path.startswith(
            "/api/auth/callback/openai"
        ):
            self._log(f"continue_url 不是 callback/openai 类型: {continue_url[:80]}")
            return None

        try:
            self._log("尝试从 create_account callback 直接获取 session token...")
            response = self.session.get(
                continue_url,
                allow_redirects=True,
                timeout=15,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "referer": "https://chatgpt.com/",
                },
            )
            self._log(f"callback 请求状态: {response.status_code}")

            session_resp = self.session.get(
                "https://chatgpt.com/api/auth/session",
                headers={
                    "accept": "application/json",
                    "referer": "https://chatgpt.com/",
                },
                timeout=15,
            )
            self._log(f"session 请求状态: {session_resp.status_code}")

            if session_resp.status_code != 200:
                self._log(f"session 接口返回 {session_resp.status_code}", "warning")
                return None

            try:
                session_data = session_resp.json()
            except Exception:
                self._log("session 接口返回非 JSON 响应", "warning")
                return None

            access_token = str(session_data.get("accessToken") or "").strip()
            if not access_token:
                self._log(
                    f"accessToken 缺失，响应 keys: {list(session_data.keys())}",
                    "warning",
                )
                return None

            self._log("从 create_account callback 成功获取 accessToken")
            return self._parse_session_jwt(access_token, session_data)

        except Exception as e:
            self._log(f"create_account callback session token 获取失败: {e}", "warning")
            return None

    def _try_direct_session_token(self) -> Optional[Dict[str, Any]]:
        """复用已有 session 直接 authorize 拿 token（避免二次登录触发 add-phone gate）"""
        if not self.session:
            return None

        import urllib.parse

        try:
            self._log("尝试直接通过已有 session 获取 token...")

            if self.oauth_start:
                try:
                    parsed_auth = urllib.parse.urlparse(self.oauth_start.auth_url)
                    auth_params = dict(urllib.parse.parse_qsl(parsed_auth.query))
                    auth_params.pop("prompt", None)
                    authorize_url = f"{parsed_auth.scheme}://{parsed_auth.netloc}{parsed_auth.path}?{urllib.parse.urlencode(auth_params)}"

                    auth_resp = self.session.get(
                        authorize_url,
                        allow_redirects=False,
                        timeout=15,
                    )
                    self._log(f"authorize 状态: {auth_resp.status_code}")

                    callback_url = None
                    current_url = str(auth_resp.headers.get("Location", "")).strip()
                    if (
                        auth_resp.status_code in {301, 302, 303, 307, 308}
                        and current_url
                    ):
                        for hop in range(8):
                            if "code=" in current_url and "state=" in current_url:
                                callback_url = current_url
                                self._log("从重定向链中提取到 callback URL")
                                break
                            try:
                                hop_resp = self.session.get(
                                    current_url,
                                    allow_redirects=False,
                                    timeout=15,
                                )
                                next_loc = str(
                                    hop_resp.headers.get("Location", "")
                                ).strip()
                                if (
                                    hop_resp.status_code
                                    not in {301, 302, 303, 307, 308}
                                    or not next_loc
                                ):
                                    final_url = str(hop_resp.url or current_url)
                                    if "code=" in final_url and "state=" in final_url:
                                        callback_url = final_url
                                    break
                                current_url = urllib.parse.urljoin(
                                    current_url, next_loc
                                )
                            except Exception as hop_exc:
                                self._log(
                                    f"重定向跳 {hop + 1} 异常: {hop_exc}", "warning"
                                )
                                break

                    if callback_url:
                        token_info = self._handle_oauth_callback(callback_url)
                        if token_info:
                            self._log("直接 authorize 成功获取 token")
                            token_info["source"] = "direct_authorize"
                            return token_info
                        self._log("callback 交换失败", "warning")

                except Exception as e:
                    self._log(f"authorize 流程异常: {e}", "warning")

            # 降级：直接访问 chatgpt.com/api/auth/session
            try:
                session_resp = self.session.get(
                    "https://chatgpt.com/api/auth/session",
                    headers={
                        "accept": "application/json",
                        "referer": "https://chatgpt.com/",
                    },
                    timeout=15,
                )
                if session_resp.status_code == 200:
                    session_data = session_resp.json()
                    access_token = str(session_data.get("accessToken") or "").strip()
                    if access_token:
                        self._log("从 /api/auth/session 直接获取到 accessToken")
                        return self._parse_session_jwt(access_token, session_data)
                    self._log(
                        f"session 响应无 accessToken, keys: {list(session_data.keys())}",
                        "warning",
                    )
                else:
                    self._log(
                        f"/api/auth/session 返回 {session_resp.status_code}", "warning"
                    )
            except Exception as e:
                self._log(f"session 接口异常: {e}", "warning")

        except Exception as e:
            self._log(f"直接 session token 获取失败: {e}", "warning")

        return None

    def _parse_session_jwt(
        self, access_token: str, session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析 accessToken JWT 并构建 token_info"""
        import base64
        import json as _json

        token_info: Dict[str, Any] = {
            "access_token": access_token,
            "source": "direct_session",
        }
        for key in ("user", "expires"):
            if key in session_data:
                token_info[key] = session_data[key]

        try:
            parts = access_token.split(".")
            if len(parts) >= 2:
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
                if isinstance(payload, dict):
                    for jwt_key, info_key in [
                        ("sub", "account_id"),
                        ("email", "email"),
                        ("exp", "expired"),
                    ]:
                        if jwt_key in payload:
                            token_info[info_key] = str(payload[jwt_key])
        except Exception as e:
            self._log(f"JWT 解析警告: {e}", "warning")

        token_info.setdefault(
            "account_id", str(session_data.get("user", {}).get("id") or "").strip()
        )
        token_info.setdefault("email", self.email or "")
        token_info["refresh_token"] = ""
        token_info["id_token"] = ""

        return token_info

    def run(self) -> RegistrationResult:
        """
        执行完整的注册流程

        Token 获取策略（按优先级）：
        1. create_account continue_url → callback/session 直接拿 token
        2. workspace 流程 → select_workspace → 重定向 → OAuth 回调
        3. 直接复用 session authorize 拿 token
        4. Cookie 提取

        Returns:
            RegistrationResult: 注册结果
        """
        result = RegistrationResult(success=False, logs=self.logs)

        try:
            self._log("=" * 60)
            self._log("开始注册流程")
            self._log("=" * 60)

            # 1. 检查 IP 地理位置
            self._log("1. 检查 IP 地理位置...")
            ip_ok, location = self._check_ip_location()
            if not ip_ok:
                result.error_message = f"IP 地理位置不支持: {location}"
                self._log(f"IP 检查失败: {location}", "error")
                return result

            self._log(f"IP 位置: {location}")

            # 2. 创建邮箱
            self._log("2. 创建邮箱...")
            if not self._create_email():
                result.error_message = "创建邮箱失败"
                return result

            result.email = self.email

            # 3. 初始化会话
            self._log("3. 初始化会话...")
            if not self._init_session():
                result.error_message = "初始化会话失败"
                return result

            # 4. 开始 OAuth 流程
            self._log("4. 开始 OAuth 授权流程...")
            if not self._start_oauth():
                result.error_message = "开始 OAuth 流程失败"
                return result

            # 5. 获取 Device ID
            self._log("5. 获取 Device ID...")
            did = self._get_device_id()
            if not did:
                result.error_message = "获取 Device ID 失败"
                return result

            # 6. 检查 Sentinel 拦截
            self._log("6. 检查 Sentinel 拦截...")
            sen_data = self._check_sentinel(did)
            if sen_data:
                self._log("Sentinel 检查通过")
            else:
                self._log("Sentinel 检查失败或未启用", "warning")

            # 7. 提交注册表单 + 解析响应判断账号状态
            self._log("7. 提交注册表单...")
            signup_result = self._submit_signup_form(did, sen_data)
            if not signup_result.success:
                result.error_message = (
                    f"提交注册表单失败: {signup_result.error_message}"
                )
                return result

            # 8. [已注册账号跳过] 注册密码
            if self._is_existing_account:
                self._log("8. [已注册账号] 跳过密码设置，OTP 已自动发送")
            else:
                self._log("8. 注册密码...")
                password_ok, password = self._register_password()
                if not password_ok:
                    result.error_message = "注册密码失败"
                    return result

            # 9. [已注册账号跳过] 发送验证码
            if self._is_existing_account:
                self._log("9. [已注册账号] 跳过发送验证码，使用自动发送的 OTP")
                self._otp_sent_at = time.time()
            else:
                self._log("9. 发送验证码...")
                if not self._send_verification_code():
                    result.error_message = "发送验证码失败"
                    return result

            # 10. 获取验证码
            self._log("10. 等待验证码...")
            code = self._get_verification_code()
            if not code:
                result.error_message = "获取验证码失败"
                return result

            # 11. 验证验证码
            self._log("11. 验证验证码...")
            if not self._validate_verification_code(code):
                result.error_message = "验证验证码失败"
                return result

            # 12. [已注册账号跳过] 创建用户账户
            if self._is_existing_account:
                self._log("12. [已注册账号] 跳过创建用户账户")
            else:
                self._log("12. 创建用户账户...")
                if not self._create_user_account():
                    result.error_message = "创建用户账户失败"
                    return result

            # 13. Token 获取（多路径降级）
            self._log("13. 获取 Token...")
            token_info: Optional[Dict[str, Any]] = None
            workspace_id = ""
            continue_url = (getattr(self, "_create_account_response", None) or {}).get(
                "continue_url"
            ) or ""

            if getattr(self, "_create_account_continue_kind", "") == "add_phone":
                self._log("post-create continue_url requires phone gate", "warning")
                result.error_message = "post-create flow requires phone gate"
                result.metadata = {
                    "email_service": self.email_service.service_type.value,
                    "proxy_used": self.proxy_url,
                    "registered_at": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "is_existing_account": self._is_existing_account,
                    "post_create_continue_url": continue_url,
                    "post_create_gate": "add_phone",
                }
                return result

            # 路径 A：从 create_account continue_url 直接拿 token
            if not token_info:
                if continue_url:
                    self._log(f"continue_url: {continue_url[:100]}")
                    token_info = self._try_create_account_callback_session_token(
                        continue_url
                    )
                    if token_info:
                        self._log("路径 A 成功: callback/session 直接获取 token")

            # 路径 B：workspace 流程 → select_workspace → 重定向 → OAuth 回调
            if not token_info:
                self._log("路径 A 失败，尝试路径 B: workspace 流程...")
                workspace_id = self._get_workspace_id() or ""
                if workspace_id:
                    self._log(f"获取到 workspace_id: {workspace_id}")
                    select_url = self._select_workspace(workspace_id)
                    if select_url:
                        callback_url = self._follow_redirects(select_url)
                        if callback_url:
                            token_info = self._handle_oauth_callback(callback_url)
                            if token_info:
                                self._log(
                                    "路径 B 成功: workspace → OAuth 回调获取 token"
                                )

            # 路径 C：直接复用 session authorize 拿 token
            if not token_info:
                self._log("路径 B 失败，尝试路径 C: 直接 session token...")
                token_info = self._try_direct_session_token()
                if token_info:
                    self._log("路径 C 成功: 直接 session 获取 token")

            # 路径 D：Cookie 提取
            if not token_info:
                self._log("路径 C 失败，尝试路径 D: Cookie 提取...")
                token_info = self._extract_token_from_cookie()
                if token_info:
                    self._log("路径 D 成功: Cookie 提取 token")

            if not token_info:
                result.error_message = "所有 token 获取路径均失败"
                return result

            # 提取账户信息
            result.account_id = token_info.get("account_id", "")
            result.access_token = token_info.get("access_token", "")
            result.refresh_token = token_info.get("refresh_token", "")
            result.id_token = token_info.get("id_token", "")
            result.password = self.password or ""
            result.source = "login" if self._is_existing_account else "register"
            result.workspace_id = workspace_id

            # 尝试获取 session_token 从 cookie
            session_cookie = self.session.cookies.get(
                "__Secure-next-auth.session-token"
            )
            if session_cookie:
                self.session_token = session_cookie
                result.session_token = session_cookie
                self._log("获取到 Session Token")

            # 14. 完成
            self._log("=" * 60)
            if self._is_existing_account:
                self._log("登录成功! (已注册账号)")
            else:
                self._log("注册成功!")
            self._log(f"邮箱: {result.email}")
            self._log(f"Account ID: {result.account_id}")
            self._log(f"Workspace ID: {result.workspace_id}")
            self._log(f"Token Source: {token_info.get('source', 'unknown')}")
            self._log("=" * 60)

            result.success = True
            result.metadata = {
                "email_service": self.email_service.service_type.value,
                "proxy_used": self.proxy_url,
                "registered_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "is_existing_account": self._is_existing_account,
                "token_source": token_info.get("source", "unknown"),
            }

            return result

        except Exception as e:
            self._log(f"注册过程中发生未预期错误: {e}", "error")
            result.error_message = str(e)
            return result

    def save_to_database(self, result: RegistrationResult) -> bool:
        """
        保存注册结果到数据库

        Args:
            result: 注册结果

        Returns:
            是否保存成功
        """
        if not result.success:
            return False

        return True  # 由 account_manager 统一处理存库
