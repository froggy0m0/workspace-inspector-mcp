import re
import subprocess
from pathlib import Path

import workspace_access


GIT_TIMEOUT_SECONDS = 10
GIT_DIFF_MAX_BYTES = 500_000
GIT_SHOW_MAX_BYTES = 500_000
GIT_LOG_DEFAULT_LIMIT = 30
GIT_LOG_MAX_LIMIT = 100
GIT_REVISION_MAX_LENGTH = 200
GIT_SIMPLE_REVISION_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+(?:~[0-9]+)?$")


def git_status(path: str) -> str:
    """검증된 workspace 디렉터리에서 git status 결과를 반환한다."""
    resolved_path = _validate_git_repository(path)
    return _git_status(resolved_path)


def git_diff(path: str) -> str:
    """검증된 workspace 디렉터리에서 git diff 결과를 반환한다."""
    resolved_path = _validate_git_repository(path)
    return _git_diff(resolved_path)


def git_log(path: str, limit: int = GIT_LOG_DEFAULT_LIMIT) -> str:
    """검증된 workspace 디렉터리에서 git log 결과를 반환한다."""
    _validate_git_log_limit(limit)
    resolved_path = _validate_git_repository(path)
    return _git_log(resolved_path, limit)


def git_show(path: str, revision: str) -> str:
    """검증된 workspace 디렉터리에서 commit 하나의 git show 결과를 반환한다."""
    _validate_git_revision(revision)
    resolved_path = _validate_git_repository(path)
    commit_sha = _resolve_git_commit(resolved_path, revision)
    return _git_show_commit(resolved_path, commit_sha)


def _validate_git_log_limit(limit: int) -> None:
    """git log 조회 개수가 허용 범위인지 확인한다."""
    if not 1 <= limit <= GIT_LOG_MAX_LIMIT:
        raise ValueError("limit은 1 이상 100 이하이어야 합니다.")


def _validate_git_revision(revision: str) -> None:
    """git show가 commit 하나만 조회하도록 단순 revision 문법만 허용한다."""
    if revision == "":
        raise ValueError("revision은 비어 있을 수 없습니다.")

    if revision != revision.strip():
        raise ValueError("revision 앞뒤 공백은 허용하지 않습니다.")

    if len(revision) > GIT_REVISION_MAX_LENGTH:
        raise ValueError(f"revision은 최대 {GIT_REVISION_MAX_LENGTH}자까지 허용합니다.")

    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in revision):
        raise ValueError("revision에는 공백이나 control 문자를 사용할 수 없습니다.")

    if revision.startswith("-"):
        raise ValueError("revision은 '-'로 시작할 수 없습니다.")

    if "^" in revision:
        raise ValueError("revision의 ^ 문법은 허용하지 않습니다. gitLog로 hash를 찾은 뒤 gitShow에 전달하세요.")

    if ":" in revision:
        raise ValueError("revision의 file/search 문법은 허용하지 않습니다.")

    if ".." in revision:
        raise ValueError("revision의 range 문법은 허용하지 않습니다.")

    if "@{" in revision:
        raise ValueError("revision의 reflog 문법은 허용하지 않습니다.")

    if not GIT_SIMPLE_REVISION_PATTERN.fullmatch(revision):
        raise ValueError("revision은 hash, branch, tag, HEAD, <revision>~N 형식만 허용합니다.")


def _validate_git_repository(path: str) -> Path:
    """path가 조회 가능한 workspace 안 git repository인지 확인한다."""
    resolved_path = workspace_access.validate_access_path(path)
    workspace_access.validate_access_directory(resolved_path)
    _validate_git_work_tree(resolved_path)
    _validate_git_top_level(resolved_path)
    return resolved_path


def _validate_git_work_tree(path: Path) -> None:
    """path가 git work tree 안인지 확인한다."""
    result = _run_git(["rev-parse", "--is-inside-work-tree"], path, check=False)

    if result.returncode != 0 or result.stdout.strip() != "true":
        message = result.stderr.strip() or "git repository가 아닙니다."
        raise RuntimeError(message)


def _validate_git_top_level(path: Path) -> None:
    """git repository 최상위 디렉터리가 workspace 안인지 확인한다."""
    result = _run_git(["rev-parse", "--show-toplevel"], path)

    top_level = Path(result.stdout.strip()).resolve()
    if not workspace_access.is_access_allowed_path(top_level):
        raise PermissionError("git repository root가 workspace 밖에 있어 차단했습니다.")


def _git_status(path: Path) -> str:
    """git status --short --branch 실행 결과를 반환한다."""
    return _run_git(["--no-optional-locks", "status", "--short", "--branch"], path).stdout


def _git_diff(path: Path) -> str:
    """git diff 실행 결과를 반환한다."""
    output = _run_git(["--no-optional-locks", "diff", "--no-ext-diff", "--no-textconv"], path).stdout
    _validate_git_diff_size(output)
    return output


def _git_log(path: Path, limit: int) -> str:
    """git log --oneline 실행 결과를 반환한다."""
    return _run_git(["log", "--oneline", "-n", str(limit)], path).stdout


def _resolve_git_commit(path: Path, revision: str) -> str:
    """사용자 revision을 실제 commit SHA로 고정한다."""
    result = _run_git(
        ["rev-parse", "--verify", "--quiet", "--end-of-options", f"{revision}^{{commit}}"],
        path,
        check=False,
    )

    commit_sha = result.stdout.strip()
    if result.returncode != 0 or commit_sha == "":
        message = result.stderr.strip() or "commit으로 해석할 수 없는 revision입니다."
        raise ValueError(message)

    return commit_sha.splitlines()[0]


def _git_show_commit(path: Path, commit_sha: str) -> str:
    """resolve된 commit SHA로 git show 결과를 반환한다."""
    output = _run_git(
        [
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
            commit_sha,
        ],
        path,
    ).stdout
    _validate_git_output_size(output, "git show", GIT_SHOW_MAX_BYTES)
    return output


def _validate_git_diff_size(output: str) -> None:
    _validate_git_output_size(output, "git diff", GIT_DIFF_MAX_BYTES)


def _validate_git_output_size(output: str, label: str, max_bytes: int) -> None:
    output_size = len(output.encode("utf-8"))
    if output_size > max_bytes:
        raise PermissionError(f"{label} output is too large: {output_size} bytes > {max_bytes} bytes")


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """공통 git 명령 실행 옵션을 고정한다."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=GIT_TIMEOUT_SECONDS,
    )

    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git 명령 실패: {result.returncode}"
        raise RuntimeError(message)

    return result
