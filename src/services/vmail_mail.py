"""
Vmail email service implementation.
"""

import logging
import random
import re
import string
import time
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional

from .base import BaseEmailService, EmailServiceError, EmailServiceType
from ..config.constants import OTP_CODE_PATTERN, OTP_CODE_SEMANTIC_PATTERN
from ..core.http_client import HTTPClient, RequestConfig


logger = logging.getLogger(__name__)


class VmailService(BaseEmailService):
    """Minimal Vmail mailbox service."""

    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        super().__init__(EmailServiceType.VMAIL, name)

        required_keys = ["base_url", "api_key"]
        missing_keys = [key for key in required_keys if not (config or {}).get(key)]
        if missing_keys:
            raise ValueError(f"Missing required config: {missing_keys}")

        default_config = {
            "default_domain": "",
            "expires_in": 86400,
            "timeout": 30,
            "max_retries": 3,
            "poll_interval": 3,
            "proxy_url": None,
        }
        self.config = {**default_config, **(config or {})}
        self.config["base_url"] = str(self.config["base_url"]).rstrip("/")
        self.config["default_domain"] = str(self.config.get("default_domain") or "").strip().lstrip("@")

        http_config = RequestConfig(
            timeout=int(self.config["timeout"]),
            max_retries=int(self.config["max_retries"]),
        )
        self.http_client = HTTPClient(
            proxy_url=self.config.get("proxy_url"),
            config=http_config,
        )

        self._mailboxes_by_id: Dict[str, Dict[str, Any]] = {}
        self._mailboxes_by_email: Dict[str, Dict[str, Any]] = {}
        self._last_used_message_ids: Dict[str, str] = {}

    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": str(self.config["api_key"]).strip(),
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _extract_error_message(self, payload: Any, default: str) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or default)
            if error:
                return str(error)
            if payload.get("message"):
                return str(payload["message"])
        return default

    def _unwrap_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            if payload.get("success") is False:
                raise EmailServiceError(self._extract_error_message(payload, "Vmail request failed"))
            if "data" in payload:
                return payload.get("data")
        return payload

    def _make_request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.config['base_url']}{path}"
        kwargs["headers"] = self._build_headers(kwargs.get("headers"))

        try:
            response = self.http_client.request(method, url, **kwargs)
            if response.status_code >= 400:
                error_message = f"Vmail API request failed: {response.status_code}"
                try:
                    error_message = self._extract_error_message(response.json(), error_message)
                except Exception:
                    error_message = response.text[:200] or error_message
                raise EmailServiceError(error_message)

            try:
                payload = response.json()
            except Exception:
                payload = {}

            return self._unwrap_payload(payload)
        except Exception as exc:
            self.update_status(False, exc)
            if isinstance(exc, EmailServiceError):
                raise
            raise EmailServiceError(f"Request failed: {method} {path} - {exc}")

    def _generate_local_part(self) -> str:
        prefix = "".join(random.choices(string.ascii_lowercase, k=7))
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=3))
        return f"{prefix}{suffix}"

    def _cache_mailbox(self, mailbox_info: Dict[str, Any]) -> None:
        mailbox_id = str(
            mailbox_info.get("account_id")
            or mailbox_info.get("service_id")
            or mailbox_info.get("id")
            or ""
        ).strip()
        email = str(mailbox_info.get("email") or "").strip().lower()

        if mailbox_id:
            self._mailboxes_by_id[mailbox_id] = mailbox_info
        if email:
            self._mailboxes_by_email[email] = mailbox_info

    def _get_cached_mailbox(
        self,
        *,
        email: Optional[str] = None,
        email_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if email_id:
            cached = self._mailboxes_by_id.get(str(email_id).strip())
            if cached:
                return cached

        if email:
            cached = self._mailboxes_by_email.get(str(email).strip().lower())
            if cached:
                return cached

        return None

    def _parse_message_time(self, value: Any) -> Optional[float]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10 ** 12:
                timestamp /= 1000.0
            return timestamp if timestamp > 0 else None

        text = str(value or "").strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    def _html_to_text(self, html_content: Any) -> str:
        if isinstance(html_content, list):
            html_content = "\n".join(str(item) for item in html_content if item)
        text = str(html_content or "")
        return unescape(re.sub(r"<[^>]+>", " ", text))

    def _sender_text(self, sender: Any) -> str:
        if isinstance(sender, dict):
            return " ".join(str(sender.get(key) or "") for key in ("name", "address")).strip()
        return str(sender or "").strip()

    def _message_search_text(self, summary: Dict[str, Any], detail: Dict[str, Any]) -> str:
        sender_text = self._sender_text(detail.get("from") or summary.get("from"))
        subject = str(detail.get("subject") or summary.get("subject") or "")
        preview = str(summary.get("preview") or "")
        text_body = str(detail.get("text") or "")
        html_body = self._html_to_text(detail.get("html"))
        return "\n".join(
            part for part in (sender_text, subject, preview, text_body, html_body) if part
        ).strip()

    def _is_openai_otp_mail(self, content: str) -> bool:
        text = str(content or "").lower()
        if "openai" not in text:
            return False
        keywords = (
            "verification code",
            "verify",
            "one-time code",
            "one time code",
            "security code",
            "your openai code",
            "验证码",
            "code is",
        )
        return any(keyword in text for keyword in keywords)

    def _extract_otp_code(self, content: str, pattern: str) -> Optional[str]:
        text = str(content or "")
        if not text:
            return None

        semantic_match = re.search(OTP_CODE_SEMANTIC_PATTERN, text, re.IGNORECASE)
        if semantic_match:
            return semantic_match.group(1)

        simple_match = re.search(pattern, text)
        if simple_match:
            return simple_match.group(1)

        return None

    def create_email(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        request_config = config or {}
        local_part = str(
            request_config.get("localPart")
            or
            request_config.get("local_part")
            or request_config.get("address")
            or request_config.get("prefix")
            or request_config.get("name")
            or self._generate_local_part()
        ).strip()
        domain = str(
            request_config.get("default_domain")
            or request_config.get("domain")
            or self.config.get("default_domain")
            or ""
        ).strip().lstrip("@")
        expires_in = request_config.get(
            "expiresIn",
            request_config.get("expires_in", self.config.get("expires_in")),
        )

        payload: Dict[str, Any] = {"localPart": local_part}
        if domain:
            payload["domain"] = domain
        if expires_in is not None:
            payload["expiresIn"] = expires_in

        mailbox = self._make_request(
            "POST",
            "/mailboxes",
            json=payload,
        )

        mailbox_id = str(mailbox.get("id") or "").strip()
        address = str(mailbox.get("address") or "").strip()
        if not mailbox_id or not address:
            raise EmailServiceError("Vmail returned incomplete mailbox data")

        email_info = {
            "email": address,
            "service_id": mailbox_id,
            "id": mailbox_id,
            "account_id": mailbox_id,
            "created_at": time.time(),
            "raw_mailbox": mailbox,
        }
        self._cache_mailbox(email_info)
        self.update_status(True)
        return email_info

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 120,
        pattern: str = OTP_CODE_PATTERN,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        mailbox_info = self._get_cached_mailbox(email=email, email_id=email_id)
        mailbox_id = str(
            (mailbox_info or {}).get("account_id")
            or (mailbox_info or {}).get("service_id")
            or email_id
            or ""
        ).strip()
        if not mailbox_id:
            logger.warning("Vmail mailbox cache missing: %s / %s", email, email_id)
            return None

        email_key = str(email or (mailbox_info or {}).get("email") or mailbox_id).strip().lower()
        last_used_message_id = self._last_used_message_ids.get(email_key)
        seen_message_ids = set()
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                messages = self._make_request(
                    "GET",
                    f"/mailboxes/{mailbox_id}/messages",
                    params={
                        "sort": "desc",
                        "limit": 20,
                    },
                )
                if isinstance(messages, dict):
                    messages = messages.get("messages") or messages.get("items") or []
                if not isinstance(messages, list):
                    messages = []

                for message in messages:
                    message_id = str(message.get("id") or "").strip()
                    if not message_id or message_id in seen_message_ids:
                        continue
                    if last_used_message_id and message_id == last_used_message_id:
                        continue

                    received_at = self._parse_message_time(message.get("receivedAt"))
                    if otp_sent_at and received_at and received_at + 1 < otp_sent_at:
                        continue

                    seen_message_ids.add(message_id)
                    detail = self._make_request(
                        "GET",
                        f"/mailboxes/{mailbox_id}/messages/{message_id}",
                    )
                    if not isinstance(detail, dict):
                        detail = {}

                    content = self._message_search_text(message, detail)
                    if not self._is_openai_otp_mail(content):
                        continue
                    code = self._extract_otp_code(content, pattern)
                    if code:
                        self._last_used_message_ids[email_key] = message_id
                        self.update_status(True)
                        return code
            except Exception as exc:
                logger.debug("Vmail poll failed: %s", exc)

            time.sleep(int(self.config.get("poll_interval") or 3))

        return None

    def list_emails(self, **kwargs) -> List[Dict[str, Any]]:
        return list(self._mailboxes_by_email.values())

    def delete_email(self, email_id: str) -> bool:
        mailbox_info = self._get_cached_mailbox(email_id=email_id) or self._get_cached_mailbox(email=email_id)
        mailbox_id = str(
            (mailbox_info or {}).get("account_id")
            or (mailbox_info or {}).get("service_id")
            or email_id
            or ""
        ).strip()
        if not mailbox_id:
            return False

        if mailbox_info:
            cached_email = str(mailbox_info.get("email") or "").strip().lower()
            if cached_email:
                self._mailboxes_by_email.pop(cached_email, None)
                self._last_used_message_ids.pop(cached_email, None)
        self._mailboxes_by_id.pop(mailbox_id, None)
        self.update_status(True)
        return True

    def check_health(self) -> bool:
        try:
            self.create_email({"name": f"healthcheck{int(time.time())}"})
            self.update_status(True)
            return True
        except Exception as exc:
            logger.warning("Vmail health check failed: %s", exc)
            self.update_status(False, exc)
            return False

    def get_email_messages(self, email_id: str, **kwargs) -> List[Dict[str, Any]]:
        mailbox_info = self._get_cached_mailbox(email_id=email_id) or self._get_cached_mailbox(email=email_id)
        mailbox_id = str(
            (mailbox_info or {}).get("account_id")
            or (mailbox_info or {}).get("service_id")
            or email_id
            or ""
        ).strip()
        if not mailbox_id:
            return []

        messages = self._make_request(
            "GET",
            f"/mailboxes/{mailbox_id}/messages",
            params={
                "sort": kwargs.get("sort", "desc"),
                "limit": kwargs.get("limit", 20),
            },
        )
        if isinstance(messages, dict):
            return messages.get("messages") or messages.get("items") or []
        return messages if isinstance(messages, list) else []

    def get_message_content(self, email_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        mailbox_info = self._get_cached_mailbox(email_id=email_id) or self._get_cached_mailbox(email=email_id)
        mailbox_id = str(
            (mailbox_info or {}).get("account_id")
            or (mailbox_info or {}).get("service_id")
            or email_id
            or ""
        ).strip()
        if not mailbox_id or not message_id:
            return None
        detail = self._make_request("GET", f"/mailboxes/{mailbox_id}/messages/{message_id}")
        return detail if isinstance(detail, dict) else None

    def get_service_info(self) -> Dict[str, Any]:
        return {
            "service_type": self.service_type.value,
            "name": self.name,
            "base_url": self.config["base_url"],
            "default_domain": self.config.get("default_domain") or "",
            "cached_mailboxes": len(self._mailboxes_by_email),
            "status": self.status.value,
        }
