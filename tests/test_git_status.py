from types import SimpleNamespace

import pytest

import workspace_inspector_mcp as mcp_server
import workspace_git_tools


# 이 파일은 gitStatus(path) MCP tool이 git status를 얇게 연결하는지만 검증한다.


def test_git_status_success(workspace_root, monkeypatch):
    """workspace 안 디렉터리를 검증한 뒤 git status 출력만 반환한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "--no-optional-locks", "status", "--short", "--branch"]:
            return SimpleNamespace(returncode=0, stdout="## main\n M app.py\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    result = mcp_server.gitStatus("repo")

    assert result == "## main\n M app.py\n"
    assert calls == [
        (
            ["git", "rev-parse", "--is-inside-work-tree"],
            {
                "cwd": repo.resolve(),
                "stdin": workspace_git_tools.subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "shell": False,
                "timeout": 10,
            },
        ),
        (
            ["git", "rev-parse", "--show-toplevel"],
            {
                "cwd": repo.resolve(),
                "stdin": workspace_git_tools.subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "shell": False,
                "timeout": 10,
            },
        ),
        (
            ["git", "--no-optional-locks", "status", "--short", "--branch"],
            {
                "cwd": repo.resolve(),
                "stdin": workspace_git_tools.subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "shell": False,
                "timeout": 10,
            },
        )
    ]


def test_git_status_blocks_bad_path(write_text):
    """기존 workspace access 정책으로 잘못된 path를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(PermissionError):
        mcp_server.gitStatus("/repo")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.gitStatus("../repo")  # workspace 밖 경로 차단

    with pytest.raises(NotADirectoryError):
        mcp_server.gitStatus("repo/README.md")  # 파일 path 차단


def test_git_status_blocks_non_git_repo(workspace_root, monkeypatch):
    """git work tree가 아니면 status 실행 전에 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="not a git repository"):
        mcp_server.gitStatus("repo")

    assert calls == [["git", "rev-parse", "--is-inside-work-tree"]]


def test_git_status_blocks_repo_root_outside_workspace(workspace_root, monkeypatch):
    """git repo root가 workspace 밖이면 status 실행 전에 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    outside_root = workspace_root.parent
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{outside_root.resolve()}\n", stderr="")
        raise AssertionError("git status must not be called")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="workspace 밖"):
        mcp_server.gitStatus("repo")

    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
    ]


def test_git_status_raises_stderr(workspace_root, monkeypatch):
    """git status 실패 시 stderr를 RuntimeError로 전달한다."""
    repo = workspace_root / "repo"
    repo.mkdir()

    def fake_run(command, **kwargs):
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "--no-optional-locks", "status", "--short", "--branch"]:
            return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="not a git repository"):
        mcp_server.gitStatus("repo")
