from pathlib import Path
import tomllib


def test_requests_dependency_is_declared_for_cloudmail():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_dependencies = pyproject["project"]["dependencies"]

    assert any(line.startswith("requests") for line in requirements)
    assert any(dep.startswith("requests") for dep in project_dependencies)
