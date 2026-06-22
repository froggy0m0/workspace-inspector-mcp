from types import SimpleNamespace

import pytest

import workspace_inspector_mcp as mcp_server
import workspace_git_tools


# 이 파일은 gitDiff(path) MCP tool이 git diff를 얇게 연결하는지만 검증한다.


def test_git_diff_success(workspace_root, monkeypatch):
    """workspace 안 git repository를 검증한 뒤 git diff 출력만 반환한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"]:
            return SimpleNamespace(returncode=0, stdout="diff --git a/app.py b/app.py\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    result = mcp_server.gitDiff("repo")

    assert result == "diff --git a/app.py b/app.py\n"
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
            ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"],
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


def test_git_diff_blocks_output_over_byte_limit(workspace_root, monkeypatch):
    """git diff UTF-8 출력이 제한을 초과하면 자르지 않고 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    monkeypatch.setattr(workspace_git_tools, "GIT_DIFF_MAX_BYTES", 5)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"]:
            return SimpleNamespace(returncode=0, stdout="가가", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="bytes"):
        mcp_server.gitDiff("repo")

    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
        ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"],
    ]


def test_git_diff_allows_output_at_byte_limit(workspace_root, monkeypatch):
    """git diff UTF-8 출력이 정확히 제한 크기이면 허용한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    monkeypatch.setattr(workspace_git_tools, "GIT_DIFF_MAX_BYTES", 6)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"]:
            return SimpleNamespace(returncode=0, stdout="가가", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    assert mcp_server.gitDiff("repo") == "가가"
    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
        ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"],
    ]


def test_git_diff_blocks_bad_path(write_text):
    """기존 workspace access 정책으로 잘못된 path를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(PermissionError):
        mcp_server.gitDiff("/repo")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.gitDiff("../repo")  # workspace 밖 경로 차단

    with pytest.raises(NotADirectoryError):
        mcp_server.gitDiff("repo/README.md")  # 파일 path 차단


def test_git_diff_blocks_non_git_repo(workspace_root, monkeypatch):
    """git work tree가 아니면 diff 실행 전에 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="not a git repository"):
        mcp_server.gitDiff("repo")

    assert calls == [["git", "rev-parse", "--is-inside-work-tree"]]


def test_git_diff_blocks_repo_root_outside_workspace(workspace_root, monkeypatch):
    """git repo root가 workspace 밖이면 diff 실행 전에 차단한다."""
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
        raise AssertionError("git diff must not be called")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="workspace 밖"):
        mcp_server.gitDiff("repo")

    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
    ]


def test_git_diff_raises_stderr(workspace_root, monkeypatch):
    """git diff 실패 시 stderr를 RuntimeError로 전달한다."""
    repo = workspace_root / "repo"
    repo.mkdir()

    def fake_run(command, **kwargs):
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"]:
            return SimpleNamespace(returncode=129, stdout="", stderr="fatal: ambiguous argument")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="ambiguous argument"):
        mcp_server.gitDiff("repo")
