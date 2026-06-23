from types import SimpleNamespace

import pytest

import workspace_inspector_mcp as mcp_server
import workspace_git_tools


# 이 파일은 gitLog(path, limit) MCP tool이 git log를 얇게 연결하는지만 검증한다.


def test_git_log_success_default_limit(workspace_root, monkeypatch):
    """기본 limit 30으로 git log 출력만 반환한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "log", "--oneline", "-n", "30"]:
            return SimpleNamespace(returncode=0, stdout="abc1234 (HEAD -> main, origin/main) message\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    result = mcp_server.gitLog("repo")

    assert result == "abc1234 (HEAD -> main, origin/main) message\n"
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
            ["git", "log", "--oneline", "-n", "30"],
            {
                "cwd": repo.resolve(),
                "stdin": workspace_git_tools.subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "shell": False,
                "timeout": 10,
            },
        ),
    ]


def test_git_log_success_max_limit(workspace_root, monkeypatch):
    """최대 limit 100으로 git log를 조회할 수 있다."""
    repo = workspace_root / "repo"
    repo.mkdir()

    def fake_run(command, **kwargs):
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "log", "--oneline", "-n", "100"]:
            return SimpleNamespace(returncode=0, stdout="abc1234 message\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    assert mcp_server.gitLog("repo", 100) == "abc1234 message\n"


def test_git_log_blocks_bad_limit():
    """limit이 1 이상 100 이하가 아니면 차단한다."""
    with pytest.raises(ValueError, match="1 이상 100 이하"):
        mcp_server.gitLog("repo", 0)

    with pytest.raises(ValueError, match="1 이상 100 이하"):
        mcp_server.gitLog("repo", 101)


def test_git_log_blocks_bad_path(write_text):
    """기존 workspace access 정책으로 잘못된 path를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(PermissionError):
        mcp_server.gitLog("/repo")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.gitLog("../repo")  # workspace 밖 경로 차단

    with pytest.raises(NotADirectoryError):
        mcp_server.gitLog("repo/README.md")  # 파일 path 차단


def test_git_log_blocks_non_git_repo(workspace_root, monkeypatch):
    """git work tree가 아니면 log 실행 전에 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="not a git repository"):
        mcp_server.gitLog("repo")

    assert calls == [["git", "rev-parse", "--is-inside-work-tree"]]


def test_git_log_blocks_repo_root_outside_workspace(workspace_root, monkeypatch):
    """git repo root가 workspace 밖이면 log 실행 전에 차단한다."""
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
        raise AssertionError("git log must not be called")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="workspace 밖"):
        mcp_server.gitLog("repo")

    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
    ]


def test_git_log_raises_stderr(workspace_root, monkeypatch):
    """git log 실패 시 stderr를 RuntimeError로 전달한다."""
    repo = workspace_root / "repo"
    repo.mkdir()

    def fake_run(command, **kwargs):
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "log", "--oneline", "-n", "30"]:
            return SimpleNamespace(returncode=128, stdout="", stderr="fatal: bad revision")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="bad revision"):
        mcp_server.gitLog("repo")
