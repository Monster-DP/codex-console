from pathlib import Path


def test_docker_start_script_uses_lf_line_endings():
    script_bytes = Path("scripts/docker/start-webui.sh").read_bytes()

    assert b"\r\n" not in script_bytes


def test_dockerfile_uses_configurable_pip_index():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ARG PIP_INDEX_URL=https://pypi.org/simple" in dockerfile
    assert 'pip install --no-cache-dir --upgrade pip -i "${PIP_INDEX_URL}"' in dockerfile
    assert 'pip install --no-cache-dir -r requirements.txt -i "${PIP_INDEX_URL}"' in dockerfile
