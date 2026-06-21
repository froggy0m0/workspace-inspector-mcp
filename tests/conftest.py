import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 테스트 수집 시 외부 환경변수 값에 흔들리지 않도록 import 전 기본 root를 고정한다.
os.environ["WORKSPACE_INSPECTOR_ROOT"] = str(PROJECT_ROOT)

import workspace_inspector_mcp as mcp_server
import workspace_access


def _resolve_test_path(workspace_root: Path, path: str) -> Path:
    """테스트 helper가 임시 workspace 밖에 파일을 만들지 못하게 막는다."""
    test_path = Path(path)
    if test_path.is_absolute() or ".." in test_path.parts:
        raise ValueError(f"테스트 파일 path는 workspace 상대경로여야 합니다: {path}")
    return workspace_root / test_path


@pytest.fixture
def workspace_root(tmp_path, monkeypatch):
    """각 테스트마다 실제 workspace 대신 임시 workspace root를 사용한다."""
    root = tmp_path / "workspace"
    root.mkdir()

    # 검증 모듈이 참조하는 root만 임시 디렉터리로 바꿔 실제 파일을 건드리지 않는다.
    monkeypatch.setattr(workspace_access, "WORKSPACE_ROOT", root.resolve())
    return root


@pytest.fixture
def write_text(workspace_root):
    """테스트용 텍스트 파일을 부모 디렉터리까지 함께 만든다."""

    def _write_text(path: str, text: str) -> Path:
        target = _resolve_test_path(workspace_root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    return _write_text


@pytest.fixture
def write_bytes(workspace_root):
    """테스트용 bytes 파일을 부모 디렉터리까지 함께 만든다."""

    def _write_bytes(path: str, data: bytes) -> Path:
        target = _resolve_test_path(workspace_root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    return _write_bytes
