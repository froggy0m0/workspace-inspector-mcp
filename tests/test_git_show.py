from types import SimpleNamespace

import pytest

import workspace_git_tools
import workspace_inspector_mcp as mcp_server


COMMIT_SHA = "4a5b999b55c55983d09f6331d8d3fb4c5b582b69"


def _git_kwargs(repo):
    """git subprocess 실행 옵션이 MCP stdio와 출력 decode 정책을 유지하는지 검증한다."""
    return {
        "cwd": repo.resolve(),
        "stdin": workspace_git_tools.subprocess.DEVNULL,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "shell": False,
        "timeout": 10,
    }


def test_git_show_success_resolves_revision_and_shows_sha(workspace_root, monkeypatch):
    """사용자 revision을 commit SHA로 resolve한 뒤 그 SHA로만 git show를 실행한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", "HEAD~1^{commit}"]:
            return SimpleNamespace(returncode=0, stdout=f"{COMMIT_SHA}\n", stderr="")
        if command == [
            "git",
            "--no-optional-locks",
            "show",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--no-notes",
            "--stat",
            "--patch",
            "--format=medium",
            "--end-of-options",
            COMMIT_SHA,
        ]:
            return SimpleNamespace(returncode=0, stdout="commit output\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    result = mcp_server.gitShow("repo", "HEAD~1")

    assert result == "commit output\n"
    assert calls == [
        (["git", "rev-parse", "--is-inside-work-tree"], _git_kwargs(repo)),
        (["git", "rev-parse", "--show-toplevel"], _git_kwargs(repo)),
        (
            ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", "HEAD~1^{commit}"],
            _git_kwargs(repo),
        ),
        (
            [
                "git",
                "--no-optional-locks",
                "show",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--no-notes",
                "--stat",
                "--patch",
                "--format=medium",
                "--end-of-options",
                COMMIT_SHA,
            ],
            _git_kwargs(repo),
        ),
    ]


@pytest.mark.parametrize("revision", ["HEAD", "main", "origin/main", "feature/foo", "v1.2.3", "4a5b999"])
def test_git_show_allows_simple_revision_forms(workspace_root, monkeypatch, revision):
    """hash, branch, tag, HEAD 같은 단순 revision은 Git commit 검증까지 넘긴다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{revision}^{{commit}}"]:
            return SimpleNamespace(returncode=0, stdout=f"{COMMIT_SHA}\n", stderr="")
        if command[-1] == COMMIT_SHA and command[:3] == ["git", "--no-optional-locks", "show"]:
            return SimpleNamespace(returncode=0, stdout="commit output\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    assert mcp_server.gitShow("repo", revision) == "commit output\n"
    assert ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{revision}^{{commit}}"] in calls


@pytest.mark.parametrize(
    "revision",
    [
        "HEAD^",
        "HEAD^2",
        "main..HEAD",
        "main...HEAD",
        "HEAD:README.md",
        "HEAD -- README.md",
        "HEAD@{1}",
        ":/fix bug",
        "--help",
        "-p",
        "",
        " HEAD",
        "HEAD ",
        "HEAD 1",
    ],
)
def test_git_show_blocks_unsupported_revision_syntax(monkeypatch, revision):
    """range, file, reflog, search, pathspec, option-like revision은 Git 실행 전에 차단한다."""
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        raise AssertionError("git must not be called")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(ValueError):
        mcp_server.gitShow("repo", revision)

    assert calls == []


def test_git_show_blocks_bad_path(write_text):
    """기존 workspace access 정책으로 잘못된 path를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(PermissionError):
        mcp_server.gitShow("/repo", "HEAD")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.gitShow("../repo", "HEAD")  # workspace 밖 경로 차단

    with pytest.raises(NotADirectoryError):
        mcp_server.gitShow("repo/README.md", "HEAD")  # 파일 path 차단


def test_git_show_blocks_non_git_repo(workspace_root, monkeypatch):
    """git work tree가 아니면 revision resolve 전에 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=128, stdout="", stderr="fatal: not a git repository")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="not a git repository"):
        mcp_server.gitShow("repo", "HEAD")

    assert calls == [["git", "rev-parse", "--is-inside-work-tree"]]


def test_git_show_blocks_repo_root_outside_workspace(workspace_root, monkeypatch):
    """git repo root가 workspace 밖이면 revision resolve 전에 차단한다."""
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
        raise AssertionError("git show must not be called")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="workspace"):
        mcp_server.gitShow("repo", "HEAD")

    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
    ]


def test_git_show_blocks_unresolvable_revision(workspace_root, monkeypatch):
    """Git이 commit으로 해석하지 못한 revision은 git show 실행 전에 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", "unknown^{commit}"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        raise AssertionError("git show must not be called")

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="commit"):
        mcp_server.gitShow("repo", "unknown")

    assert calls == [
        ["git", "rev-parse", "--is-inside-work-tree"],
        ["git", "rev-parse", "--show-toplevel"],
        ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", "unknown^{commit}"],
    ]


def test_git_show_blocks_output_over_byte_limit(workspace_root, monkeypatch):
    """git show UTF-8 출력이 제한을 초과하면 반환하지 않고 차단한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    monkeypatch.setattr(workspace_git_tools, "GIT_SHOW_MAX_BYTES", 5)

    def fake_run(command, **kwargs):
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", "HEAD^{commit}"]:
            return SimpleNamespace(returncode=0, stdout=f"{COMMIT_SHA}\n", stderr="")
        if command[-1] == COMMIT_SHA and command[:3] == ["git", "--no-optional-locks", "show"]:
            return SimpleNamespace(returncode=0, stdout="가가", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    with pytest.raises(PermissionError, match="bytes"):
        mcp_server.gitShow("repo", "HEAD")


def test_git_show_allows_output_at_byte_limit(workspace_root, monkeypatch):
    """git show UTF-8 출력이 정확히 제한 크기이면 허용한다."""
    repo = workspace_root / "repo"
    repo.mkdir()
    monkeypatch.setattr(workspace_git_tools, "GIT_SHOW_MAX_BYTES", 6)

    def fake_run(command, **kwargs):
        if command == ["git", "rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return SimpleNamespace(returncode=0, stdout=f"{repo.resolve()}\n", stderr="")
        if command == ["git", "rev-parse", "--verify", "--quiet", "--end-of-options", "HEAD^{commit}"]:
            return SimpleNamespace(returncode=0, stdout=f"{COMMIT_SHA}\n", stderr="")
        if command[-1] == COMMIT_SHA and command[:3] == ["git", "--no-optional-locks", "show"]:
            return SimpleNamespace(returncode=0, stdout="가가", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(workspace_git_tools.subprocess, "run", fake_run)

    assert mcp_server.gitShow("repo", "HEAD") == "가가"
