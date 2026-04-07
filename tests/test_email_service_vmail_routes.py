import asyncio
from contextlib import contextmanager
from pathlib import Path

from src.config.constants import EmailServiceType
from src.database.models import Base, EmailService
from src.database.session import DatabaseSessionManager
from src.services.base import EmailServiceFactory
from src.web.routes import email as email_routes
from src.web.routes import registration as registration_routes


class DummySettings:
    tempmail_enabled = False
    yyds_mail_enabled = False
    yyds_mail_api_key = None
    custom_domain_base_url = ""
    custom_domain_api_key = None


def test_vmail_service_registered():
    service_type = EmailServiceType("vmail")
    service_class = EmailServiceFactory.get_service_class(service_type)
    assert service_class is not None
    assert service_class.__name__ == "VmailService"


def test_email_service_types_include_vmail():
    result = asyncio.run(email_routes.get_service_types())
    vmail_type = next(item for item in result["types"] if item["value"] == "vmail")

    assert vmail_type["label"] == "Vmail"
    field_names = [field["name"] for field in vmail_type["config_fields"]]
    assert "base_url" in field_names
    assert "api_key" in field_names
    assert "default_domain" in field_names


def test_filter_sensitive_config_marks_vmail_api_key():
    filtered = email_routes.filter_sensitive_config({
        "base_url": "https://vmail.dev/api/v1",
        "api_key": "vmail_test_key",
        "default_domain": "example.com",
    })

    assert filtered["base_url"] == "https://vmail.dev/api/v1"
    assert filtered["default_domain"] == "example.com"
    assert filtered["has_api_key"] is True
    assert "api_key" not in filtered


def test_registration_available_services_include_vmail(monkeypatch):
    runtime_dir = Path("tests_runtime")
    runtime_dir.mkdir(exist_ok=True)
    db_path = runtime_dir / "vmail_routes.db"
    if db_path.exists():
        db_path.unlink()

    manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=manager.engine)

    with manager.session_scope() as session:
        session.add(
            EmailService(
                service_type="vmail",
                name="Vmail 主服务",
                config={
                    "base_url": "https://vmail.dev/api/v1",
                    "api_key": "vmail_test_key",
                    "default_domain": "example.com",
                    "expires_in": 86400,
                },
                enabled=True,
                priority=0,
            )
        )

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(registration_routes, "get_db", fake_get_db)

    import src.config.settings as settings_module

    monkeypatch.setattr(settings_module, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(registration_routes, "get_settings", lambda: DummySettings())

    result = asyncio.run(registration_routes.get_available_email_services())

    assert result["vmail"]["available"] is True
    assert result["vmail"]["count"] == 1
    assert result["vmail"]["services"][0]["name"] == "Vmail 主服务"
    assert result["vmail"]["services"][0]["type"] == "vmail"
    assert result["vmail"]["services"][0]["default_domain"] == "example.com"
