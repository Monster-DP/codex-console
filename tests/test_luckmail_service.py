import pytest

from src.services.base import EmailServiceError
from src.services.luckmail_mail import LuckMailService


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


class FakeHTTPClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "kwargs": kwargs,
            }
        )
        if not self.responses:
            raise AssertionError(f"未准备响应: {method} {url}")
        return self.responses.pop(0)


def test_luckmail_service_uses_builtin_http_client_for_healthcheck():
    service = LuckMailService(
        {
            "base_url": "https://mails.luckyous.com",
            "api_key": "ak_test_key",
            "project_code": "openai",
        }
    )
    fake_client = FakeHTTPClient(
        [
            FakeResponse(
                payload={
                    "code": 0,
                    "message": "success",
                    "data": {
                        "balance": "0.9880",
                    },
                }
            ),
        ]
    )
    service.client.user.session = fake_client

    assert service.check_health() is True

    call = fake_client.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://mails.luckyous.com/api/v1/openapi/user/info"
    assert call["kwargs"]["headers"]["X-API-Key"] == "ak_test_key"


def test_luckmail_service_can_purchase_email_and_fetch_code_without_external_sdk():
    service = LuckMailService(
        {
            "base_url": "https://mails.luckyous.com",
            "api_key": "ak_test_key",
            "project_code": "openai",
            "email_type": "ms_graph",
            "reuse_existing_purchases": False,
        }
    )
    fake_client = FakeHTTPClient(
        [
            FakeResponse(
                payload={
                    "code": 0,
                    "message": "success",
                    "data": {
                        "list": [
                            {
                                "id": 2,
                                "name": "OpenAI",
                                "code": "openai",
                                "prices": [
                                    {
                                        "email_type": "ms_graph",
                                        "stock": 12,
                                        "buy_price": "0.0100",
                                    }
                                ],
                            }
                        ]
                    },
                }
            ),
            FakeResponse(
                payload={
                    "code": 0,
                    "message": "success",
                    "data": {
                        "purchases": [
                            {
                                "id": 7,
                                "email_address": "tester@outlook.com",
                                "token": "tok_abc123",
                                "project_name": "OpenAI",
                                "price": "2.0000",
                            }
                        ],
                    },
                }
            ),
            FakeResponse(
                payload={
                    "code": 0,
                    "message": "success",
                    "data": {
                        "email_address": "tester@outlook.com",
                        "project": "OpenAI",
                        "has_new_mail": True,
                        "verification_code": "654321",
                        "mail": {
                            "message_id": "msg_001",
                            "from": "noreply@openai.com",
                            "subject": "Your verification code",
                        },
                    },
                }
            ),
        ]
    )
    service.client.user.session = fake_client

    email_info = service.create_email()
    code = service.get_verification_code(
        email=email_info["email"],
        email_id=email_info["service_id"],
        timeout=1,
    )

    assert email_info["email"] == "tester@outlook.com"
    assert email_info["service_id"] == "tok_abc123"
    assert code == "654321"

    project_call = fake_client.calls[0]
    assert project_call["method"] == "GET"
    assert project_call["url"] == "https://mails.luckyous.com/api/v1/openapi/projects"

    purchase_call = fake_client.calls[1]
    assert purchase_call["method"] == "POST"
    assert purchase_call["url"] == "https://mails.luckyous.com/api/v1/openapi/email/purchase"
    assert purchase_call["kwargs"]["headers"]["X-API-Key"] == "ak_test_key"
    assert purchase_call["kwargs"]["json"] == {
        "project_code": "openai",
        "quantity": 1,
        "email_type": "ms_graph",
    }

    code_call = fake_client.calls[2]
    assert code_call["method"] == "GET"
    assert code_call["url"] == "https://mails.luckyous.com/api/v1/openapi/email/token/tok_abc123/code"
    assert "X-API-Key" not in code_call["kwargs"]["headers"]


def test_luckmail_service_reports_project_specific_out_of_stock_before_purchase():
    service = LuckMailService(
        {
            "base_url": "https://mails.luckyous.com",
            "api_key": "ak_test_key",
            "project_code": "openai",
            "email_type": "ms_graph",
            "reuse_existing_purchases": False,
        }
    )
    fake_client = FakeHTTPClient(
        [
            FakeResponse(
                payload={
                    "code": 0,
                    "message": "success",
                    "data": {
                        "list": [
                            {
                                "id": 2,
                                "name": "OpenAI",
                                "code": "openai",
                                "prices": [
                                    {
                                        "email_type": "ms_graph",
                                        "stock": 0,
                                        "buy_price": "0.0100",
                                    },
                                    {
                                        "email_type": "ms_imap",
                                        "stock": 0,
                                        "buy_price": "0.0100",
                                    },
                                ],
                            }
                        ]
                    },
                }
            ),
        ]
    )
    service.client.user.session = fake_client

    with pytest.raises(EmailServiceError) as exc_info:
        service.create_email()

    assert (
        str(exc_info.value)
        == "LuckMail 项目 openai 的邮箱类型 ms_graph 当前库存为 0（项目 OpenAI）。平台价格页显示的可能是全站库存，请更换 project_code 或等待补货"
    )
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["url"] == "https://mails.luckyous.com/api/v1/openapi/projects"
