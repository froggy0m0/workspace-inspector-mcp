import pytest

import workspace_inspector_mcp as mcp_server


# 이 파일은 listDir(path) MCP tool의 동작만 검증한다.


def test_list_dir_success_orders_dirs_first(workspace_root, write_text):
    """디렉터리는 '/' suffix를 붙이고 파일보다 먼저 이름순으로 반환한다."""
    (workspace_root / "repo/src").mkdir(parents=True)
    (workspace_root / "repo/docs").mkdir(parents=True)
    write_text("repo/README.md", "hello\n")
    write_text("repo/build.gradle", "plugins {}\n")

    result = mcp_server.listDir("repo")

    assert result == [
        "docs/",
        "src/",
        "build.gradle",
        "README.md",
    ]


def test_list_dir_returns_empty_list(workspace_root):
    """비어 있는 디렉터리는 빈 list를 반환한다."""
    (workspace_root / "repo/empty").mkdir(parents=True)

    result = mcp_server.listDir("repo/empty")

    assert result == []


def test_list_dir_hides_blocked_dirs(workspace_root):
    """BLOCKED_DIRS는 목록에서 숨긴다."""
    (workspace_root / "repo").mkdir()
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        (workspace_root / f"repo/{blocked_dir}").mkdir()  # 차단 디렉터리 생성
    (workspace_root / "repo/src").mkdir()

    result = mcp_server.listDir("repo")

    assert result == ["src/"]


def test_list_dir_blocks_bad_path(workspace_root):
    """절대경로, workspace 밖 경로, Windows 경로 문자를 차단한다."""
    (workspace_root / "repo").mkdir()

    with pytest.raises(PermissionError):
        mcp_server.listDir("/tmp/repo")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.listDir("../repo")  # workspace 밖 경로 차단

    with pytest.raises(PermissionError):
        mcp_server.listDir("C:\\Users\\x")  # Windows 경로 문자 차단


def test_list_dir_blocks_blocked_dir_path(workspace_root):
    """차단 디렉터리 자체를 listDir 대상으로 지정해도 차단한다."""
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        (workspace_root / f"repo/{blocked_dir}").mkdir(parents=True)  # 차단 디렉터리 생성

        with pytest.raises(PermissionError):
            mcp_server.listDir(f"repo/{blocked_dir}")  # 차단 디렉터리 접근 차단


def test_list_dir_blocks_missing_directory(workspace_root):
    """workspace 안 경로여도 디렉터리가 없으면 FileNotFoundError를 낸다."""
    with pytest.raises(FileNotFoundError):
        mcp_server.listDir("repo/missing")  # 존재하지 않는 디렉터리 차단


def test_list_dir_blocks_file_path(write_text):
    """listDir은 디렉터리 목록 tool이라 파일 path를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(NotADirectoryError):
        mcp_server.listDir("repo/README.md")  # 파일 path 차단
