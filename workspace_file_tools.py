import os
from pathlib import Path

import workspace_access


MAX_READ_BYTES = 1_000_000
MAX_RANGE_LINES = 300
MAX_FIND_PATTERN_LENGTH = 128
MAX_FIND_RESULTS = 500
MAX_FIND_ENTRIES = 50_000
MAX_SEARCH_QUERY_LENGTH = 128
MAX_SEARCH_RESULTS = 200


def read_file(path: str) -> str:
    """검증된 workspace 상대경로의 작은 텍스트 파일 하나를 읽는다."""
    resolved_path = workspace_access.validate_access_path(path)
    return _read_text_file(resolved_path)


def read_file_range(path: str, startLine: int, endLine: int) -> str:
    """검증된 workspace 상대경로의 텍스트 파일 일부 줄 범위를 읽는다."""
    resolved_path = workspace_access.validate_access_path(path)
    _validate_read_range(startLine, endLine)
    return _read_text_file_range(resolved_path, startLine, endLine)


def list_dir(path: str) -> list[str]:
    """검증된 workspace 상대경로의 디렉터리 목록을 반환한다."""
    resolved_path = workspace_access.validate_access_path(path)
    workspace_access.validate_access_directory(resolved_path)

    entries = []
    # 디렉터리를 먼저 보여주고, 같은 종류 안에서는 이름순으로 정렬한다.
    for child in sorted(resolved_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        # listDir도 차단 디렉터리 이름은 노출하지 않는다.
        if child.name in workspace_access.BLOCKED_DIRS:
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(f"{child.name}{suffix}")

    return entries


def find_files(path: str, pattern: str) -> list[str]:
    """검증된 workspace 상대경로의 디렉터리 아래에서 파일명을 재귀 검색한다."""
    resolved_path = workspace_access.validate_access_path(path)
    workspace_access.validate_access_directory(resolved_path)
    pattern = _validate_find_pattern(pattern)
    return _find_files(resolved_path, pattern)


def search_text(path: str, query: str) -> list[str]:
    """검증된 workspace 상대경로의 디렉터리 아래에서 텍스트 내용을 검색한다."""
    resolved_path = workspace_access.validate_access_path(path)
    workspace_access.validate_access_directory(resolved_path)
    query = _validate_search_query(query)
    return _search_text(resolved_path, query)


def _read_text_file(resolved_path: Path) -> str:
    """접근 검증을 통과한 작은 텍스트 파일 내용을 반환한다."""
    if not resolved_path.exists():
        raise FileNotFoundError("파일이 존재하지 않습니다.")

    if not resolved_path.is_file():
        raise IsADirectoryError("파일이 아닙니다.")

    size = resolved_path.stat().st_size
    if size > MAX_READ_BYTES:
        raise PermissionError(f"파일이 너무 큽니다: {size} bytes > {MAX_READ_BYTES} bytes")

    # 전체 파일을 bytes로 본 뒤 NUL byte가 있으면 바이너리로 보고 차단한다.
    data = resolved_path.read_bytes()
    if b"\x00" in data:
        raise PermissionError("바이너리 파일로 판단되어 읽기를 차단했습니다.")

    # 소스 파일 확인 목적이라 UTF-8 오류는 치환해서 최대한 내용을 보여준다.
    return data.decode("utf-8", errors="replace")


def _validate_read_range(startLine: int, endLine: int) -> None:
    """요청한 줄 범위가 안전한지 확인한다."""
    if not isinstance(startLine, int) or not isinstance(endLine, int):
        raise ValueError("줄 번호는 정수여야 합니다.")

    if startLine < 1:
        raise ValueError("시작 줄 번호는 1 이상이어야 합니다.")

    if endLine < startLine:
        raise ValueError("끝 줄 번호는 시작 줄 번호보다 크거나 같아야 합니다.")

    # 너무 큰 범위 요청은 MCP 응답이 과도하게 커지므로 제한한다.
    line_count = endLine - startLine + 1
    if line_count > MAX_RANGE_LINES:
        raise ValueError(f"한 번에 읽을 수 있는 범위는 최대 {MAX_RANGE_LINES}줄입니다.")


def _read_text_file_range(resolved_path: Path, startLine: int, endLine: int) -> str:
    """접근 검증을 통과한 텍스트 파일에서 요청한 줄 범위만 반환한다."""
    if not resolved_path.exists():
        raise FileNotFoundError("파일이 존재하지 않습니다.")

    if not resolved_path.is_file():
        raise IsADirectoryError("파일이 아닙니다.")

    lines = []
    with resolved_path.open("rb") as file:
        # 필요한 줄까지만 순차적으로 읽어 큰 파일 전체를 메모리에 올리지 않는다.
        for line_number, raw_line in enumerate(file, start=1):
            if line_number > endLine:
                break

            # 범위 읽기에서도 NUL byte가 발견되면 텍스트가 아니라고 보고 중단한다.
            if b"\x00" in raw_line:
                raise PermissionError("바이너리 파일로 판단되어 읽기를 차단했습니다.")

            if line_number < startLine:
                continue

            lines.append(raw_line)

    return b"".join(lines).decode("utf-8", errors="replace")


def _validate_find_pattern(pattern: str) -> str:
    """파일명 검색 패턴이 단순 문자열인지 확인한다."""
    if not isinstance(pattern, str):
        raise ValueError("검색 패턴은 문자열이어야 합니다.")

    # findFiles는 glob/regex가 아니라 파일명 literal substring 검색만 지원한다.
    normalized_pattern = pattern.strip()
    if normalized_pattern == "":
        raise ValueError("검색 패턴이 비어 있습니다.")

    if len(normalized_pattern) > MAX_FIND_PATTERN_LENGTH:
        raise ValueError(f"검색 패턴이 너무 깁니다: {len(normalized_pattern)} chars > {MAX_FIND_PATTERN_LENGTH} chars")

    if "/" in normalized_pattern or "\\" in normalized_pattern or ":" in normalized_pattern or ".." in normalized_pattern:
        raise PermissionError("검색 패턴에는 경로 문자를 사용할 수 없습니다.")

    return normalized_pattern


def _find_files(resolved_path: Path, pattern: str) -> list[str]:
    """접근 검증을 통과한 디렉터리 아래에서 파일명에 pattern이 들어간 파일을 찾는다."""
    pattern_lower = pattern.casefold()
    inspected_entries = 0
    matches = []
    # 재귀 탐색은 직접 stack을 사용해 탐색 개수 제한을 명확히 적용한다.
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

            # 차단 디렉터리는 내려가지도, 결과로 내보내지도 않는다.
            if child.name in workspace_access.BLOCKED_DIRS:
                continue

            try:
                # symlink는 workspace 밖 우회 가능성이 있어 파일/디렉터리 모두 탐색하지 않는다.
                if child.is_symlink():
                    continue
            except OSError:
                continue

            try:
                child_resolved = child.resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            # resolve 이후에도 workspace 접근 정책을 다시 적용한다.
            if not workspace_access.is_access_allowed_path(child_resolved):
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
                # MCP 응답은 항상 workspace 기준 상대경로와 "/" 구분자로 반환한다.
                matches.append(child_resolved.relative_to(workspace_access.WORKSPACE_ROOT).as_posix())
                if len(matches) > MAX_FIND_RESULTS:
                    raise PermissionError(f"검색 결과가 너무 많습니다: {len(matches)} files > {MAX_FIND_RESULTS} files")

    return sorted(matches, key=str.casefold)


def _validate_search_query(query: str) -> str:
    """텍스트 검색어가 단순 문자열인지 확인한다."""
    if not isinstance(query, str):
        raise ValueError("검색어는 문자열이어야 합니다.")

    # searchText도 regex가 아니라 단순 문자열 검색만 지원한다.
    normalized_query = query.strip()
    if normalized_query == "":
        raise ValueError("검색어가 비어 있습니다.")

    if len(normalized_query) > MAX_SEARCH_QUERY_LENGTH:
        raise ValueError(f"검색어가 너무 깁니다: {len(normalized_query)} chars > {MAX_SEARCH_QUERY_LENGTH} chars")

    if "\x00" in normalized_query:
        raise PermissionError("검색어에 NUL 문자는 사용할 수 없습니다.")

    return normalized_query


def _can_search_dir(path: Path) -> bool:
    """검색 중 내려가도 되는 디렉터리인지 확인한다."""
    try:
        # os.walk가 내려가기 전에 symlink와 workspace 접근 정책을 함께 확인한다.
        return not path.is_symlink() and workspace_access.is_access_allowed_path(path.resolve(strict=False))
    except (OSError, RuntimeError):
        return False


def _search_text(resolved_path: Path, query: str) -> list[str]:
    """접근 검증을 통과한 디렉터리 아래 텍스트 파일 내용에서 query를 찾는다."""
    query_lower = query.casefold()
    results = []

    for dirpath, dirnames, filenames in os.walk(resolved_path):
        current_dir = Path(dirpath)

        # dirnames를 제자리 수정해야 os.walk가 차단/허용 안 된 디렉터리로 내려가지 않는다.
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames, key=str.casefold)
            if dirname not in workspace_access.BLOCKED_DIRS and _can_search_dir(current_dir / dirname)
        ]

        for filename in sorted(filenames, key=str.casefold):
            file_path = current_dir / filename

            try:
                # 파일 symlink도 내용 검색 대상에서 제외한다.
                if file_path.is_symlink():
                    continue
                file_resolved = file_path.resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            if not workspace_access.is_access_allowed_path(file_resolved):
                continue

            try:
                if not file_path.is_file():
                    continue

                with file_path.open("rb") as file:
                    for line_number, raw_line in enumerate(file, start=1):
                        # 파일 중간에 NUL byte가 나오면 해당 파일은 바이너리로 보고 더 읽지 않는다.
                        if b"\x00" in raw_line:
                            break

                        # 깨진 UTF-8은 치환해서 검색/표시한다.
                        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                        if query_lower not in line.casefold():
                            continue

                        # 검색 결과는 rg 스타일에 가깝게 path:line: content 형식으로 반환한다.
                        relative_path = file_resolved.relative_to(workspace_access.WORKSPACE_ROOT).as_posix()
                        results.append(f"{relative_path}:{line_number}: {line}")
                        if len(results) > MAX_SEARCH_RESULTS:
                            raise ValueError(f"검색 결과가 너무 많습니다: {len(results)} lines > {MAX_SEARCH_RESULTS} lines")
            except OSError:
                continue

    return results
