from src.services.vmail_mail import VmailService


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
        self.calls.append({
            "method": method,
            "url": url,
            "kwargs": kwargs,
        })
        if not self.responses:
            raise AssertionError(f"未准备响应: {method} {url}")
        return self.responses.pop(0)


def test_vmail_create_email_uses_api_key_and_optional_domain():
    service = VmailService({
        "base_url": "https://vmail.dev/api/v1",
        "api_key": "vmail_test_key",
        "default_domain": "example.com",
        "expires_in": 86400,
    })
    fake_client = FakeHTTPClient([
        FakeResponse(
            status_code=201,
            payload={
                "data": {
                    "id": "mbx_123",
                    "address": "tester@example.com",
                    "domain": "example.com",
                    "expiresAt": "2026-04-07T16:00:00.000Z",
                    "createdAt": "2026-04-07T15:00:00.000Z",
                }
            },
        ),
    ])
    service.http_client = fake_client

    email_info = service.create_email({"name": "tester"})

    assert email_info["email"] == "tester@example.com"
    assert email_info["service_id"] == "mbx_123"
    assert email_info["id"] == "mbx_123"
    assert email_info["account_id"] == "mbx_123"

    create_call = fake_client.calls[0]
    assert create_call["method"] == "POST"
    assert create_call["url"] == "https://vmail.dev/api/v1/mailboxes"
    assert create_call["kwargs"]["headers"]["X-API-Key"] == "vmail_test_key"
    assert create_call["kwargs"]["json"] == {
        "localPart": "tester",
        "domain": "example.com",
        "expiresIn": 86400,
    }


def test_vmail_get_verification_code_fetches_messages_and_detail():
    service = VmailService({
        "base_url": "https://vmail.dev/api/v1",
        "api_key": "vmail_test_key",
    })
    fake_client = FakeHTTPClient([
        FakeResponse(
            payload={
                "data": [
                    {
                        "id": "msg_001",
                        "from": {"address": "noreply@openai.com", "name": "OpenAI"},
                        "subject": "Your verification code",
                        "preview": "Your OpenAI verification code is 654321",
                        "receivedAt": "2026-04-07T10:30:00.000Z",
                    }
                ],
                "pagination": {
                    "page": 1,
                    "limit": 20,
                    "total": 1,
                    "totalPages": 1,
                    "hasMore": False,
                },
            }
        ),
        FakeResponse(
            payload={
                "data": {
                    "id": "msg_001",
                    "messageId": "<unique-id@sender.com>",
                    "from": {"address": "noreply@openai.com", "name": "OpenAI"},
                    "to": [{"address": "tester@example.com", "name": ""}],
                    "cc": [],
                    "bcc": [],
                    "replyTo": [],
                    "subject": "Your verification code",
                    "text": "Your OpenAI verification code is 654321",
                    "html": "<p>Your OpenAI verification code is <strong>654321</strong></p>",
                    "headers": [{"name": "X-Custom", "value": "value"}],
                    "receivedAt": "2026-04-07T10:30:00.000Z",
                }
            }
        ),
    ])
    service.http_client = fake_client
    service._cache_mailbox({
        "email": "tester@example.com",
        "service_id": "mbx_123",
        "id": "mbx_123",
        "account_id": "mbx_123",
    })

    code = service.get_verification_code(
        email="tester@example.com",
        email_id="mbx_123",
        timeout=1,
    )

    assert code == "654321"

    list_call = fake_client.calls[0]
    assert list_call["method"] == "GET"
    assert list_call["url"] == "https://vmail.dev/api/v1/mailboxes/mbx_123/messages"
    assert list_call["kwargs"]["headers"]["X-API-Key"] == "vmail_test_key"
    assert list_call["kwargs"]["params"]["sort"] == "desc"

    detail_call = fake_client.calls[1]
    assert detail_call["method"] == "GET"
    assert detail_call["url"] == "https://vmail.dev/api/v1/mailboxes/mbx_123/messages/msg_001"
    assert detail_call["kwargs"]["headers"]["X-API-Key"] == "vmail_test_key"


def test_vmail_check_health_uses_mailbox_create_endpoint():
    service = VmailService({
        "base_url": "https://vmail.dev/api/v1",
        "api_key": "vmail_test_key",
    })
    fake_client = FakeHTTPClient([
        FakeResponse(
            status_code=201,
            payload={
                "data": {
                    "id": "mbx_health",
                    "address": "healthcheck@vmail.dev",
                }
            },
        ),
    ])
    service.http_client = fake_client

    assert service.check_health() is True

    health_call = fake_client.calls[0]
    assert health_call["method"] == "POST"
    assert health_call["url"] == "https://vmail.dev/api/v1/mailboxes"
    assert health_call["kwargs"]["headers"]["X-API-Key"] == "vmail_test_key"
