"""
LuckMail 内置 HTTP 客户端。

用于在外部 SDK 不可用时，直接对接 LuckMail OpenAPI。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests


class LuckMailApiError(RuntimeError):
    """LuckMail OpenAPI 调用失败。"""


def _to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_namespace(val) for key, val in value.items()})
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


class _LuckMailBuiltinUserClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self, include_api_key: bool = True, include_json: bool = False) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
        }
        if include_api_key:
            headers["X-API-Key"] = self.api_key
        if include_json:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        include_api_key: bool = True,
    ) -> Any:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=self._headers(include_api_key=include_api_key, include_json=json is not None),
            params=params,
            json=json,
            timeout=self.timeout,
        )

        try:
            payload = response.json()
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise LuckMailApiError(f"LuckMail 返回了无法解析的响应: {response.text[:200]}") from exc

        if response.status_code >= 400:
            raise LuckMailApiError(str(payload.get("message") or response.text or f"HTTP {response.status_code}"))

        code = payload.get("code")
        if code not in (0, "0", None):
            raise LuckMailApiError(str(payload.get("message") or "LuckMail 请求失败"))

        return _to_namespace(payload.get("data"))

    def get_info(self) -> Any:
        return self._request("GET", "/api/v1/openapi/user/info")

    def get_balance(self) -> Any:
        return self.get_info()

    def create_order(
        self,
        *,
        project_code: str,
        email_type: Optional[str] = None,
        domain: Optional[str] = None,
        specified_email: Optional[str] = None,
        variant_mode: Optional[str] = None,
    ) -> Any:
        payload: Dict[str, Any] = {
            "project_code": project_code,
        }
        if email_type:
            payload["email_type"] = email_type
        if domain:
            payload["domain"] = domain
        if specified_email:
            payload["specified_email"] = specified_email
        if variant_mode:
            payload["variant_mode"] = variant_mode
        return self._request("POST", "/api/v1/openapi/order/create", json=payload)

    def get_order_code(self, order_no: str) -> Any:
        return self._request("GET", f"/api/v1/openapi/order/{quote(str(order_no), safe='')}/code")

    def cancel_order(self, order_no: str) -> Any:
        return self._request("POST", f"/api/v1/openapi/order/{quote(str(order_no), safe='')}/cancel")

    def get_orders(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Any:
        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }
        if status is not None:
            params["status"] = status
        if project_id is not None:
            params["project_id"] = project_id
        return self._request("GET", "/api/v1/openapi/orders", params=params)

    def purchase_emails(
        self,
        *,
        project_code: str,
        quantity: int,
        email_type: Optional[str] = None,
        domain: Optional[str] = None,
        variant_mode: Optional[str] = None,
    ) -> Any:
        payload: Dict[str, Any] = {
            "project_code": project_code,
            "quantity": quantity,
        }
        if email_type:
            payload["email_type"] = email_type
        if domain:
            payload["domain"] = domain
        if variant_mode:
            payload["variant_mode"] = variant_mode
        return self._request("POST", "/api/v1/openapi/email/purchase", json=payload)

    def get_projects(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> Any:
        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }
        return self._request("GET", "/api/v1/openapi/projects", params=params)

    def get_purchases(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        project_id: Optional[int] = None,
        tag_id: Optional[int] = None,
        keyword: Optional[str] = None,
        user_disabled: Optional[int] = None,
    ) -> Any:
        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }
        if project_id is not None:
            params["project_id"] = project_id
        if tag_id is not None:
            params["tag_id"] = tag_id
        if keyword:
            params["keyword"] = keyword
        if user_disabled is not None:
            params["user_disabled"] = user_disabled
        return self._request("GET", "/api/v1/openapi/email/purchases", params=params)

    def set_purchase_disabled(self, purchase_id: int, disabled: int) -> Any:
        return self._request(
            "PUT",
            f"/api/v1/openapi/email/purchases/{int(purchase_id)}/disabled",
            json={"disabled": disabled},
        )

    def get_token_code(self, token: str) -> Any:
        return self._request(
            "GET",
            f"/api/v1/openapi/email/token/{quote(str(token), safe='')}/code",
            include_api_key=False,
        )

    def create_appeal(self, **payload: Any) -> Any:
        return self._request("POST", "/api/v1/openapi/appeal/create", json=payload)


class LuckMailClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.user = _LuckMailBuiltinUserClient(base_url=base_url, api_key=api_key, timeout=timeout)
