from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_registration_ui_surfaces_failure_reason_in_toast():
    content = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "toast.error(`注册失败: ${data.error || data.message || '未知错误'}`)" in content


def test_registration_ui_contains_vmail_available_service_bucket():
    content = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "vmail: { available: false, services: [] }" in content
