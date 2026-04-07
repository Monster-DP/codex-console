from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_services_test_action_surfaces_backend_message():
    content = (ROOT / "static" / "js" / "email_services.js").read_text(encoding="utf-8")

    assert "toast.error('测试失败: ' + (result.error || result.message || '未知错误'))" in content
