import pytest

import workspace_inspector_mcp as mcp_server
import workspace_file_tools
import workspace_access


# 이 파일은 searchText(path, query) MCP tool의 동작만 검증한다.


def test_search_text_success(write_text):
    """query가 들어간 줄만 workspace 상대경로와 줄 번호로 반환한다."""
    write_text("repo/src/BoardController.java", "class BoardController {}\n")
    write_text("repo/src/BoardService.java", "class BoardService {}\n")

    result = mcp_server.searchText("repo", "BoardController")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_case_insensitive(write_text):
    """검색어는 대소문자를 구분하지 않는다."""
    write_text("repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "boardcontroller")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_no_match(write_text):
    """검색 결과가 없으면 빈 list를 반환한다."""
    write_text("repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "MissingText")

    assert result == []


def test_search_text_strips_query(write_text):
    """query 앞뒤 공백은 제거한 뒤 검색한다."""
    write_text("repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "  BoardController  ")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_blocks_bad_path(write_text):
    """절대경로, workspace 밖 경로, Windows 경로 문자를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(PermissionError):
        mcp_server.searchText("/tmp/repo", "hello")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.searchText("../repo", "hello")  # workspace 밖 경로 차단

    with pytest.raises(PermissionError):
        mcp_server.searchText("C:\\Users\\x", "hello")  # Windows 경로 문자 차단


def test_search_text_blocks_file_path(write_text):
    """searchText는 디렉터리 검색 tool이라 파일 path를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(NotADirectoryError):
        mcp_server.searchText("repo/README.md", "hello")  # 파일 path 차단


def test_search_text_blocks_bad_query(write_text):
    """빈 query, 너무 긴 query, NUL 포함 query를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(ValueError):
        mcp_server.searchText("repo", "")  # 빈 검색어 차단

    with pytest.raises(ValueError):
        mcp_server.searchText("repo", " ")  # 공백만 있는 검색어 차단

    with pytest.raises(ValueError):
        mcp_server.searchText("repo", "x" * 129)  # 128자 초과 검색어 차단

    with pytest.raises(PermissionError):
        mcp_server.searchText("repo", "a\x00b")  # NUL 포함 검색어 차단


def test_search_text_skips_blocked_dirs(write_text):
    """BLOCKED_DIRS 안의 파일은 내용이 매칭되어도 검색하지 않는다."""
    for blocked_dir in sorted(workspace_access.BLOCKED_DIRS):
        write_text(f"repo/{blocked_dir}/hidden.txt", "secret-value\n")  # 차단 디렉터리별 매칭 파일 생성

    write_text("repo/src/App.java", "public class App {}\n")

    result = mcp_server.searchText("repo", "secret-value")

    assert result == []


def test_search_text_blocks_blocked_dir_path(workspace_root):
    """차단 디렉터리 자체를 searchText 시작 path로 지정해도 차단한다."""
    for blocked_dir in sorted(workspace_access.BLOCKED_DIRS):
        (workspace_root / f"repo/{blocked_dir}").mkdir(parents=True)  # 차단 디렉터리 생성

        with pytest.raises(PermissionError):
            mcp_server.searchText(f"repo/{blocked_dir}", "secret-value")  # 차단 디렉터리 시작 path 차단


def test_search_text_skips_symlinks(workspace_root, write_text):
    """symlink 파일과 symlink 디렉터리는 검색하지 않는다."""
    write_text("outside/link-file.txt", "link-secret\n")
    write_text("outside-dir/hidden.txt", "link-secret\n")
    write_text("repo/src/App.java", "public class App {}\n")

    try:
        # Windows는 개발자 모드/권한이 없으면 symlink 생성 자체가 막히므로 이 정책 테스트만 건너뛴다.
        (workspace_root / "repo/link-file.txt").symlink_to(workspace_root / "outside/link-file.txt")  # symlink 파일 생성
        (workspace_root / "repo/link-dir").symlink_to(workspace_root / "outside-dir", target_is_directory=True)  # symlink 디렉터리 생성
    except OSError as exc:
        pytest.skip(f"symlink 생성 권한이 없어 테스트를 건너뜁니다: {exc}")

    result = mcp_server.searchText("repo", "link-secret")

    assert result == []


def test_search_text_stops_binary_file(write_bytes, write_text):
    """NUL byte가 나오면 바이너리로 보고 해당 파일만 검색 중단한다."""
    write_bytes("repo/binary.bin", b"BoardController\x00hidden\nBoardController\n")
    write_text("repo/src/BoardController.java", "class BoardController {}\n")

    result = mcp_server.searchText("repo", "BoardController")

    assert result == [
        "repo/src/BoardController.java:1: class BoardController {}",
    ]


def test_search_text_replaces_invalid_utf8(write_bytes):
    """깨진 UTF-8 byte는 replacement char로 바꾸고 검색은 계속한다."""
    write_bytes("repo/broken.txt", b"broken-\xff BoardController\n")

    result = mcp_server.searchText("repo", "BoardController")

    assert result == [
        "repo/broken.txt:1: broken-\ufffd BoardController",
    ]


def test_search_text_result_limit(write_text):
    """검색 결과가 MAX_SEARCH_RESULTS를 넘으면 차단한다."""
    lines = "\n".join("needle" for _ in range(workspace_file_tools.MAX_SEARCH_RESULTS + 1))
    write_text("repo/many.txt", lines)

    with pytest.raises(ValueError):
        mcp_server.searchText("repo", "needle")  # 결과 제한 초과 차단
