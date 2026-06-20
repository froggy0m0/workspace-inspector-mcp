"""
workspace-inspector MCP 함수 직접 테스트입니다.

이 파일은 MCP 서버 구현 참고용 코드가 아닙니다.
실제 MCP 서버 진입점은 ../workspace_inspector_mcp.py 입니다.

테스트 흐름:
1. TemporaryDirectory로 가짜 workspace를 만든다.
2. 테스트 동안 mcp_server.WORKSPACE_ROOT만 가짜 workspace로 바꾼다.
3. 테스트용 파일/디렉터리를 만든다.
4. searchText()를 직접 호출한다.
5. 정상 결과 또는 기대 예외를 확인한다.
6. WORKSPACE_ROOT를 원래 값으로 되돌린다.
"""

import sys
import os
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("WORKSPACE_INSPECTOR_ROOT", str(PROJECT_ROOT))

# pytest 자동 수집 대상이 아니라, 직접 실행하는 테스트 파일이다.
__test__ = False

import workspace_inspector_mcp as mcp_server


# 공통 테스트 helper
def expect_error(error_type, func, *args):
    """차단 케이스에서 지정한 예외가 발생하는지 확인한다."""
    try:
        func(*args)
    except error_type:
        return
    raise AssertionError(f"{error_type.__name__} 예외가 발생해야 합니다.")


def write_text(path: Path, text: str) -> None:
    """부모 디렉터리를 포함해 테스트용 텍스트 파일을 만든다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    """부모 디렉터리를 포함해 테스트용 bytes 파일을 만든다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def run_with_temp_workspace(test_func):
    """실제 workspace를 건드리지 않도록 테스트마다 isolated root를 만든다."""
    original_root = mcp_server.WORKSPACE_ROOT
    with TemporaryDirectory() as temp_dir:
        mcp_server.WORKSPACE_ROOT = Path(temp_dir).resolve()
        try:
            test_func(mcp_server.WORKSPACE_ROOT)
        finally:
            mcp_server.WORKSPACE_ROOT = original_root


# 정상 동작 테스트
def test_search_text_success(root: Path) -> None:
    """query가 들어간 줄만 workspace 상대경로와 줄 번호로 반환한다."""
    write_text(root / "repo/src/BoardController.java", "class BoardController {}\n")
    write_text(root / "repo/src/BoardService.java", "class BoardService {}\n")

    result = mcp_server.searchText("repo", "BoardController")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_case_insensitive(root: Path) -> None:
    """검색은 대소문자를 구분하지 않는다."""
    write_text(root / "repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "boardcontroller")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_no_match(root: Path) -> None:
    """검색 결과가 없으면 빈 리스트를 반환한다."""
    write_text(root / "repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "MissingText")

    assert result == []


# 입력 차단 테스트
def test_search_text_blocks_bad_path(root: Path) -> None:
    """절대경로, workspace 밖 경로, Windows 경로 문자를 차단한다."""
    write_text(root / "repo/README.md", "hello\n")

    expect_error(PermissionError, mcp_server.searchText, "/tmp/repo", "hello")  # 절대경로 차단
    expect_error(PermissionError, mcp_server.searchText, "../repo", "hello")  # workspace 밖 경로 차단
    expect_error(PermissionError, mcp_server.searchText, "C:\\Users\\x", "hello")  # Windows 경로 문자 차단


def test_search_text_blocks_file_path(root: Path) -> None:
    """searchText는 디렉터리 검색 tool이라 파일 path를 차단한다."""
    write_text(root / "repo/README.md", "hello\n")

    expect_error(NotADirectoryError, mcp_server.searchText, "repo/README.md", "hello")  # 파일 path 차단


def test_search_text_blocks_bad_query(root: Path) -> None:
    """빈 query, 너무 긴 query, NUL 포함 query를 차단한다."""
    write_text(root / "repo/README.md", "hello\n")

    expect_error(ValueError, mcp_server.searchText, "repo", "")  # 빈 검색어 차단
    expect_error(ValueError, mcp_server.searchText, "repo", " ")  # 공백만 있는 검색어 차단
    expect_error(ValueError, mcp_server.searchText, "repo", "x" * 129)  # 128자 초과 검색어 차단
    expect_error(PermissionError, mcp_server.searchText, "repo", "a\x00b")  # NUL 포함 검색어 차단


# 탐색 정책 테스트
def test_search_text_skips_blocked_dirs(root: Path) -> None:
    """BLOCKED_DIRS 안 파일은 내용이 매칭되어도 검색하지 않는다."""
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        write_text(root / f"repo/{blocked_dir}/hidden.txt", "secret-value\n")  # 차단 디렉터리별 매칭 파일 생성

    write_text(root / "repo/src/App.java", "public class App {}\n")

    result = mcp_server.searchText("repo", "secret-value")

    assert result == []


def test_search_text_skips_symlinks(root: Path) -> None:
    """symlink 파일과 symlink 디렉터리는 검색하지 않는다."""
    write_text(root / "outside/link-file.txt", "link-secret\n")
    write_text(root / "outside-dir/hidden.txt", "link-secret\n")
    write_text(root / "repo/src/App.java", "public class App {}\n")

    (root / "repo/link-file.txt").symlink_to(root / "outside/link-file.txt")  # symlink 파일 생성
    (root / "repo/link-dir").symlink_to(root / "outside-dir", target_is_directory=True)  # symlink 디렉터리 생성

    result = mcp_server.searchText("repo", "link-secret")

    assert result == []


def test_search_text_stops_binary_file(root: Path) -> None:
    """NUL byte가 나오면 바이너리로 보고 해당 파일만 검색 중단한다."""
    write_bytes(root / "repo/binary.bin", b"BoardController\x00hidden\nBoardController\n")
    write_text(root / "repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "BoardController")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_replaces_invalid_utf8(root: Path) -> None:
    """깨진 UTF-8 byte는 � 로 바꾸고 검색은 계속한다."""
    write_bytes(root / "repo/broken.txt", b"broken-\xff BoardController\n")

    result = mcp_server.searchText("repo", "BoardController")

    assert result == [
        "repo/broken.txt:1: broken-\ufffd BoardController",
    ]


def test_search_text_result_limit(root: Path) -> None:
    """검색 결과가 MAX_SEARCH_RESULTS를 넘으면 차단한다."""
    lines = "\n".join("needle" for _ in range(mcp_server.MAX_SEARCH_RESULTS + 1))
    write_text(root / "repo/many.txt", lines)

    expect_error(ValueError, mcp_server.searchText, "repo", "needle")


def main() -> None:
    """pytest 없이 직접 실행하는 간단한 runner."""
    tests = [
        test_search_text_success,
        test_search_text_case_insensitive,
        test_search_text_no_match,
        test_search_text_blocks_bad_path,
        test_search_text_blocks_file_path,
        test_search_text_blocks_bad_query,
        test_search_text_skips_blocked_dirs,
        test_search_text_skips_symlinks,
        test_search_text_stops_binary_file,
        test_search_text_replaces_invalid_utf8,
        test_search_text_result_limit,
    ]

    for test in tests:
        run_with_temp_workspace(test)
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
