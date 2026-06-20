import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("workspace-inspector")

WORKSPACE_ROOT_ENV = "WORKSPACE_INSPECTOR_ROOT"

if WORKSPACE_ROOT_ENV not in os.environ:
    raise RuntimeError(f"{WORKSPACE_ROOT_ENV} 환경변수가 필요합니다.")

# 이 MCP 서버가 읽을 수 있는 최상위 workspace는 환경변수로 지정한다.
WORKSPACE_ROOT = Path(os.environ[WORKSPACE_ROOT_ENV]).resolve()
if not WORKSPACE_ROOT.exists():
    raise RuntimeError(f"{WORKSPACE_ROOT_ENV} 경로가 존재하지 않습니다.")

if not WORKSPACE_ROOT.is_dir():
    raise RuntimeError(f"{WORKSPACE_ROOT_ENV}는 디렉터리여야 합니다.")

# 소스 읽기 목적에서 내부 설정/메타데이터 디렉터리는 어디에 있든 차단한다.
BLOCKED_DIRS = {".git", ".agents", ".codex", ".idea"}
MAX_READ_BYTES = 1_000_000
MAX_RANGE_LINES = 300
MAX_FIND_PATTERN_LENGTH = 128
MAX_FIND_RESULTS = 500
MAX_FIND_ENTRIES = 50_000
MAX_SEARCH_QUERY_LENGTH = 128
MAX_SEARCH_RESULTS = 200


def validate_workspace_path(path: str) -> Path:
    """입력 path를 검증하고 workspace 내부의 resolved full path를 반환한다."""
    if not path or path.strip() == "":
        raise PermissionError("읽을 파일 경로가 비어 있습니다.")

    if "\\" in path or ":" in path:
        raise PermissionError(f"Windows/UNC 경로는 허용하지 않습니다. workspace 기준 상대경로를 사용하세요: {path}")

    user_path = Path(path)
    if user_path.is_absolute():
        raise PermissionError(f"절대경로는 허용하지 않습니다: {path}")

    resolved_path = (WORKSPACE_ROOT / user_path).resolve(strict=False)

    if resolved_path != WORKSPACE_ROOT and WORKSPACE_ROOT not in resolved_path.parents:
        raise PermissionError(f"workspace 밖 경로 접근을 차단했습니다: {path}")

    relative_parts = resolved_path.relative_to(WORKSPACE_ROOT).parts
    blocked_parts = sorted(BLOCKED_DIRS.intersection(relative_parts))
    if blocked_parts:
        raise PermissionError(f"차단된 디렉터리 접근입니다: {', '.join(blocked_parts)}")

    return resolved_path


def read_validated_file(resolved_path: Path) -> str:
    """검증된 경로의 작은 텍스트 파일 내용을 반환한다."""
    if not resolved_path.exists():
        raise FileNotFoundError("파일이 존재하지 않습니다.")

    if not resolved_path.is_file():
        raise IsADirectoryError("파일이 아닙니다.")

    size = resolved_path.stat().st_size
    if size > MAX_READ_BYTES:
        raise PermissionError(f"파일이 너무 큽니다: {size} bytes > {MAX_READ_BYTES} bytes")

    data = resolved_path.read_bytes()
    if b"\x00" in data:
        raise PermissionError("바이너리 파일로 판단되어 읽기를 차단했습니다.")

    return data.decode("utf-8", errors="replace")


def validate_line_range(startLine: int, endLine: int) -> None:
    """요청한 줄 범위가 안전한지 확인한다."""
    if not isinstance(startLine, int) or not isinstance(endLine, int):
        raise ValueError("줄 번호는 정수여야 합니다.")

    if startLine < 1:
        raise ValueError("시작 줄 번호는 1 이상이어야 합니다.")

    if endLine < startLine:
        raise ValueError("끝 줄 번호는 시작 줄 번호보다 크거나 같아야 합니다.")

    line_count = endLine - startLine + 1
    if line_count > MAX_RANGE_LINES:
        raise ValueError(f"한 번에 읽을 수 있는 범위는 최대 {MAX_RANGE_LINES}줄입니다.")


def read_validated_file_range(resolved_path: Path, startLine: int, endLine: int) -> str:
    """검증된 경로의 텍스트 파일에서 요청한 줄 범위만 반환한다."""
    if not resolved_path.exists():
        raise FileNotFoundError("파일이 존재하지 않습니다.")

    if not resolved_path.is_file():
        raise IsADirectoryError("파일이 아닙니다.")

    lines = []
    with resolved_path.open("rb") as file:
        for line_number, raw_line in enumerate(file, start=1):
            if line_number > endLine:
                break

            if b"\x00" in raw_line:
                raise PermissionError("바이너리 파일로 판단되어 읽기를 차단했습니다.")

            if line_number < startLine:
                continue

            lines.append(raw_line)

    return b"".join(lines).decode("utf-8", errors="replace")


def validate_directory(resolved_path: Path) -> None:
    """검증된 경로가 디렉터리인지 확인한다."""
    if not resolved_path.exists():
        raise FileNotFoundError("디렉터리가 존재하지 않습니다.")

    if not resolved_path.is_dir():
        raise NotADirectoryError("디렉터리가 아닙니다.")


def validate_find_pattern(pattern: str) -> str:
    """파일명 검색 패턴이 단순 문자열인지 확인한다."""
    if not isinstance(pattern, str):
        raise ValueError("검색 패턴은 문자열이어야 합니다.")

    normalized_pattern = pattern.strip()
    if normalized_pattern == "":
        raise ValueError("검색 패턴이 비어 있습니다.")

    if len(normalized_pattern) > MAX_FIND_PATTERN_LENGTH:
        raise ValueError(f"검색 패턴이 너무 깁니다: {len(normalized_pattern)} chars > {MAX_FIND_PATTERN_LENGTH} chars")

    if "/" in normalized_pattern or "\\" in normalized_pattern or ":" in normalized_pattern or ".." in normalized_pattern:
        raise PermissionError("검색 패턴에는 경로 문자를 사용할 수 없습니다.")

    return normalized_pattern


def is_searchable_path(resolved_path: Path) -> bool:
    """검색 중 발견한 경로가 workspace 내부이고 차단 디렉터리 밖인지 확인한다."""
    if resolved_path != WORKSPACE_ROOT and WORKSPACE_ROOT not in resolved_path.parents:
        return False

    relative_parts = resolved_path.relative_to(WORKSPACE_ROOT).parts
    return not BLOCKED_DIRS.intersection(relative_parts)


def find_validated_files(resolved_path: Path, pattern: str) -> list[str]:
    """검증된 디렉터리 아래에서 파일명에 pattern이 들어간 파일을 찾는다."""
    pattern_lower = pattern.casefold()
    inspected_entries = 0
    matches = []
    directories = [resolved_path]

    while directories:
        directory = directories.pop()

        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            continue

        for child in children:
            inspected_entries += 1
            if inspected_entries > MAX_FIND_ENTRIES:
                raise PermissionError(f"검색한 항목 수가 너무 많습니다: {inspected_entries} entries > {MAX_FIND_ENTRIES} entries")

            if child.name in BLOCKED_DIRS:
                continue

            try:
                if child.is_symlink():
                    continue
            except OSError:
                continue

            try:
                child_resolved = child.resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            if not is_searchable_path(child_resolved):
                continue

            try:
                child_is_dir = child.is_dir()
                child_is_file = child.is_file()
            except OSError:
                continue

            if child_is_dir:
                directories.append(child)
                continue

            if child_is_file and pattern_lower in child.name.casefold():
                matches.append(child_resolved.relative_to(WORKSPACE_ROOT).as_posix())
                if len(matches) > MAX_FIND_RESULTS:
                    raise PermissionError(f"검색 결과가 너무 많습니다: {len(matches)} files > {MAX_FIND_RESULTS} files")

    return sorted(matches, key=str.casefold)


def validate_search_query(query: str) -> str:
    """텍스트 검색어가 단순 문자열인지 확인한다."""
    if not isinstance(query, str):
        raise ValueError("검색어는 문자열이어야 합니다.")

    normalized_query = query.strip()
    if normalized_query == "":
        raise ValueError("검색어가 비어 있습니다.")

    if len(normalized_query) > MAX_SEARCH_QUERY_LENGTH:
        raise ValueError(f"검색어가 너무 깁니다: {len(normalized_query)} chars > {MAX_SEARCH_QUERY_LENGTH} chars")

    if "\x00" in normalized_query:
        raise PermissionError("검색어에 NUL 문자는 사용할 수 없습니다.")

    return normalized_query


def can_search_dir(path: Path) -> bool:
    """검색 중 내려가도 되는 디렉터리인지 확인한다."""
    try:
        return not path.is_symlink() and is_searchable_path(path.resolve(strict=False))
    except (OSError, RuntimeError):
        return False


def search_validated_text(resolved_path: Path, query: str) -> list[str]:
    """검증된 디렉터리 아래 텍스트 파일 내용에서 query를 찾는다."""
    query_lower = query.casefold()
    results = []

    for dirpath, dirnames, filenames in os.walk(resolved_path):
        current_dir = Path(dirpath)

        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames, key=str.casefold)
            if dirname not in BLOCKED_DIRS and can_search_dir(current_dir / dirname)
        ]

        for filename in sorted(filenames, key=str.casefold):
            file_path = current_dir / filename

            try:
                if file_path.is_symlink():
                    continue
                file_resolved = file_path.resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            if not is_searchable_path(file_resolved):
                continue

            try:
                if not file_path.is_file():
                    continue

                with file_path.open("rb") as file:
                    for line_number, raw_line in enumerate(file, start=1):
                        if b"\x00" in raw_line:
                            break

                        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                        if query_lower not in line.casefold():
                            continue

                        relative_path = file_resolved.relative_to(WORKSPACE_ROOT).as_posix()
                        results.append(f"{relative_path}:{line_number}: {line}")
                        if len(results) > MAX_SEARCH_RESULTS:
                            raise ValueError(f"검색 결과가 너무 많습니다: {len(results)} lines > {MAX_SEARCH_RESULTS} lines")
            except OSError:
                continue

    return results


@mcp.tool()
def readFile(path: str) -> str:
    """
    설정된 workspace root 기준 상대경로의 작은 텍스트 파일 하나를 읽는다.

    메타정보를 붙이지 않고 파일 내용만 반환한다.
    """
    resolved_path = validate_workspace_path(path)
    return read_validated_file(resolved_path)


@mcp.tool()
def readFileRange(path: str, startLine: int, endLine: int) -> str:
    """
    설정된 workspace root 기준 상대경로의 텍스트 파일 일부 줄 범위를 읽는다.

    메타정보나 줄 번호를 붙이지 않고 요청 범위의 내용만 반환한다.
    """
    resolved_path = validate_workspace_path(path)
    validate_line_range(startLine, endLine)
    return read_validated_file_range(resolved_path, startLine, endLine)


@mcp.tool()
def listDir(path: str) -> list[str]:
    """
    설정된 workspace root 기준 상대경로의 디렉터리 목록을 반환한다.

    디렉터리는 이름 뒤에 "/"를 붙인다.
    """
    resolved_path = validate_workspace_path(path)
    validate_directory(resolved_path)

    entries = []
    for child in sorted(resolved_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name in BLOCKED_DIRS:
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")

    return entries


@mcp.tool()
def findFiles(path: str, pattern: str) -> list[str]:
    """
    설정된 workspace root 기준 상대경로의 디렉터리 아래에서 파일명을 재귀 검색한다.

    파일 내용은 읽지 않고, 파일명에 pattern이 들어간 파일 경로만 반환한다.
    """
    resolved_path = validate_workspace_path(path)
    validate_directory(resolved_path)
    validated_pattern = validate_find_pattern(pattern)
    return find_validated_files(resolved_path, validated_pattern)


@mcp.tool()
def searchText(path: str, query: str) -> list[str]:
    """
    설정된 workspace root 기준 상대경로의 디렉터리 아래에서 텍스트 내용을 검색한다.

    파일 경로, 줄 번호, 해당 줄을 문자열로 반환한다.
    """
    resolved_path = validate_workspace_path(path)
    validate_directory(resolved_path)
    validated_query = validate_search_query(query)
    return search_validated_text(resolved_path, validated_query)


if __name__ == "__main__":
    mcp.run()
