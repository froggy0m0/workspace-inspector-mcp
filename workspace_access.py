import os
from pathlib import Path


def load_workspace_root(env_name: str = "WORKSPACE_INSPECTOR_ROOT") -> Path:
    """환경변수에서 workspace root를 읽고 사용할 수 있는 디렉터리인지 확인한다."""
    if env_name not in os.environ:
        raise RuntimeError(f"{env_name} 환경변수가 필요합니다.")

    # 이후 모든 path 검증은 이 root를 기준으로 계산하므로 먼저 절대경로로 고정한다.
    workspace_root = Path(os.environ[env_name]).resolve()
    if not workspace_root.exists():
        raise RuntimeError(f"{env_name} 경로가 존재하지 않습니다.")

    if not workspace_root.is_dir():
        raise RuntimeError(f"{env_name}는 디렉터리여야 합니다.")

    return workspace_root


# MCP 서버가 접근할 수 있는 최상위 workspace.
WORKSPACE_ROOT = load_workspace_root()

# 소스 읽기 목적에서 내부 설정/메타데이터 디렉터리는 어디에 있든 차단한다.
BLOCKED_DIRS = {".git", ".agents", ".codex", ".idea"}


def validate_access_path(path: str) -> Path:
    """입력 path의 workspace 접근 가능 여부를 검증하고 resolved full path를 반환한다."""
    if not path or path.strip() == "":
        raise PermissionError("읽을 파일 경로가 비어 있습니다.")

    # MCP tool에는 workspace 기준 상대경로만 받는다. Windows/UNC 경로는 초기에 차단한다.
    if "\\" in path or ":" in path:
        raise PermissionError(f"Windows/UNC 경로는 허용하지 않습니다. workspace 기준 상대경로를 사용하세요: {path}")

    user_path = Path(path)
    if user_path.is_absolute():
        raise PermissionError(f"절대경로는 허용하지 않습니다: {path}")

    # ".." 같은 우회 시도까지 반영한 최종 경로를 만든다. 파일 존재 여부는 뒤 tool에서 확인한다.
    resolved_path = (WORKSPACE_ROOT / user_path).resolve(strict=False)

    # 최종 경로가 workspace root 밖으로 나가면 차단한다.
    if resolved_path != WORKSPACE_ROOT and WORKSPACE_ROOT not in resolved_path.parents:
        raise PermissionError(f"workspace 밖 경로 접근을 차단했습니다: {path}")

    # workspace 기준 path 조각으로 바꿔 .git 같은 차단 디렉터리가 중간에 있는지 확인한다.
    relative_parts = resolved_path.relative_to(WORKSPACE_ROOT).parts
    blocked_parts = sorted(BLOCKED_DIRS.intersection(relative_parts))
    if blocked_parts:
        raise PermissionError(f"차단된 디렉터리 접근입니다: {', '.join(blocked_parts)}")

    return resolved_path


def validate_access_directory(resolved_path: Path) -> None:
    """접근 검증을 통과한 경로가 디렉터리인지 확인한다."""
    if not resolved_path.exists():
        raise FileNotFoundError("디렉터리가 존재하지 않습니다.")

    if not resolved_path.is_dir():
        raise NotADirectoryError("디렉터리가 아닙니다.")


def is_access_allowed_path(resolved_path: Path) -> bool:
    """탐색 중 발견한 경로가 workspace 내부이고 차단 디렉터리 밖인지 확인한다."""
    # 재귀 탐색 중 발견한 symlink/특수 경로가 workspace 밖을 가리키면 내려가지 않는다.
    if resolved_path != WORKSPACE_ROOT and WORKSPACE_ROOT not in resolved_path.parents:
        return False

    # 직접 요청 path가 아니어도 탐색 중 차단 디렉터리를 만나면 결과에서 제외한다.
    relative_parts = resolved_path.relative_to(WORKSPACE_ROOT).parts
    return not BLOCKED_DIRS.intersection(relative_parts)
