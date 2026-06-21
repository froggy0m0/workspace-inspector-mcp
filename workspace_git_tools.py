import subprocess
from pathlib import Path

import workspace_access


GIT_TIMEOUT_SECONDS = 10


def git_status(path: str) -> str:
    """검증된 workspace 디렉터리에서 git status 결과를 반환한다."""
    resolved_path = workspace_access.validate_access_path(path)
    workspace_access.validate_access_directory(resolved_path)
    _validate_git_work_tree(resolved_path)
    _validate_git_top_level(resolved_path)
    return _git_status(resolved_path)


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


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    """공통 git 명령 실행 옵션을 고정한다."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=False,
        timeout=GIT_TIMEOUT_SECONDS,
    )

    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git 명령 실패: {result.returncode}"
        raise RuntimeError(message)

    return result
