import pytest

import workspace_inspector_mcp as mcp_server


# 이 파일은 findFiles(path, pattern) MCP tool의 동작만 검증한다.


def test_find_files_success_recursive_case_insensitive(write_text):
    """파일명을 재귀 검색하고 대소문자는 구분하지 않는다."""
    write_text("repo/src/BoardController.java", "class BoardController {}\n")
    write_text("repo/src/nested/board-service.java", "class BoardService {}\n")
    write_text("repo/src/App.java", "class App {}\n")

    result = mcp_server.findFiles("repo", "board")

    assert result == [
        "repo/src/BoardController.java",
        "repo/src/nested/board-service.java",
    ]


def test_find_files_returns_empty_when_no_match(write_text):
    """매칭되는 파일명이 없으면 빈 list를 반환한다."""
    write_text("repo/src/App.java", "class App {}\n")

    result = mcp_server.findFiles("repo", "Board")

    assert result == []


def test_find_files_matches_file_name_only(write_text, workspace_root):
    """디렉터리명에 pattern이 있어도 파일명에 없으면 매칭하지 않는다."""
    (workspace_root / "repo/BoardPackage").mkdir(parents=True)
    write_text("repo/BoardPackage/App.java", "class App {}\n")

    result = mcp_server.findFiles("repo", "Board")

    assert result == []


def test_find_files_returns_files_only(workspace_root, write_text):
    """pattern이 디렉터리명에 매칭되어도 파일 결과만 반환한다."""
    (workspace_root / "repo/BoardDirectory").mkdir(parents=True)
    write_text("repo/BoardFile.java", "class BoardFile {}\n")

    result = mcp_server.findFiles("repo", "Board")

    assert result == ["repo/BoardFile.java"]


def test_find_files_strips_pattern(write_text):
    """pattern 앞뒤 공백은 제거한 뒤 검색한다."""
    write_text("repo/BoardController.java", "class BoardController {}\n")

    result = mcp_server.findFiles("repo", "  Board  ")

    assert result == ["repo/BoardController.java"]


def test_find_files_blocks_bad_path(write_text):
    """절대경로, workspace 밖 경로, Windows 경로 문자를 차단한다."""
    write_text("repo/BoardController.java", "class BoardController {}\n")

    with pytest.raises(PermissionError):
        mcp_server.findFiles("/tmp/repo", "Board")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.findFiles("../repo", "Board")  # workspace 밖 경로 차단

    with pytest.raises(PermissionError):
        mcp_server.findFiles("C:\\Users\\x", "Board")  # Windows 경로 문자 차단


def test_find_files_blocks_file_path(write_text):
    """findFiles는 디렉터리 검색 tool이라 파일 path를 차단한다."""
    write_text("repo/BoardController.java", "class BoardController {}\n")

    with pytest.raises(NotADirectoryError):
        mcp_server.findFiles("repo/BoardController.java", "Board")  # 파일 path 차단


def test_find_files_blocks_bad_pattern(write_text):
    """빈 pattern, 너무 긴 pattern, 경로 문자가 들어간 pattern을 차단한다."""
    write_text("repo/BoardController.java", "class BoardController {}\n")

    with pytest.raises(ValueError):
        mcp_server.findFiles("repo", "")  # 빈 pattern 차단

    with pytest.raises(ValueError):
        mcp_server.findFiles("repo", " ")  # 공백만 있는 pattern 차단

    with pytest.raises(ValueError):
        mcp_server.findFiles("repo", "x" * 129)  # 128자 초과 pattern 차단

    with pytest.raises(PermissionError):
        mcp_server.findFiles("repo", "src/Board")  # slash 포함 pattern 차단

    with pytest.raises(PermissionError):
        mcp_server.findFiles("repo", "src\\Board")  # backslash 포함 pattern 차단

    with pytest.raises(PermissionError):
        mcp_server.findFiles("repo", "C:Board")  # colon 포함 pattern 차단

    with pytest.raises(PermissionError):
        mcp_server.findFiles("repo", "..")  # path traversal 느낌의 pattern 차단


def test_find_files_skips_blocked_dirs(write_text):
    """BLOCKED_DIRS 아래 파일은 파일명이 매칭되어도 검색하지 않는다."""
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        write_text(f"repo/{blocked_dir}/BoardHidden.java", "class BoardHidden {}\n")  # 차단 디렉터리별 매칭 파일 생성

    write_text("repo/src/App.java", "class App {}\n")

    result = mcp_server.findFiles("repo", "Board")

    assert result == []


def test_find_files_blocks_blocked_dir_path(workspace_root):
    """차단 디렉터리 자체를 findFiles 시작 path로 지정해도 차단한다."""
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        (workspace_root / f"repo/{blocked_dir}").mkdir(parents=True)  # 차단 디렉터리 생성

        with pytest.raises(PermissionError):
            mcp_server.findFiles(f"repo/{blocked_dir}", "Board")  # 차단 디렉터리 시작 path 차단


def test_find_files_skips_symlinks(workspace_root, write_text):
    """symlink 파일과 symlink 디렉터리는 검색하지 않는다."""
    write_text("outside/BoardLink.java", "class BoardLink {}\n")
    write_text("outside-dir/BoardHidden.java", "class BoardHidden {}\n")
    write_text("repo/src/App.java", "class App {}\n")

    try:
        # Windows는 개발자 모드/권한이 없으면 symlink 생성 자체가 막히므로 이 정책 테스트만 건너뛴다.
        (workspace_root / "repo/BoardLink.java").symlink_to(workspace_root / "outside/BoardLink.java")  # symlink 파일 생성
        (workspace_root / "repo/link-dir").symlink_to(workspace_root / "outside-dir", target_is_directory=True)  # symlink 디렉터리 생성
    except OSError as exc:
        pytest.skip(f"symlink 생성 권한이 없어 테스트를 건너뜁니다: {exc}")

    result = mcp_server.findFiles("repo", "Board")

    assert result == []


def test_find_files_blocks_result_limit(write_text, monkeypatch):
    """검색 결과가 MAX_FIND_RESULTS를 넘으면 차단한다."""
    monkeypatch.setattr(mcp_server, "MAX_FIND_RESULTS", 1)
    write_text("repo/BoardOne.java", "class BoardOne {}\n")
    write_text("repo/BoardTwo.java", "class BoardTwo {}\n")

    with pytest.raises(PermissionError):
        mcp_server.findFiles("repo", "Board")  # 결과 제한 초과 차단


def test_find_files_blocks_entry_limit(write_text, monkeypatch):
    """탐색한 entry 수가 MAX_FIND_ENTRIES를 넘으면 차단한다."""
    monkeypatch.setattr(mcp_server, "MAX_FIND_ENTRIES", 2)
    write_text("repo/a.txt", "a\n")
    write_text("repo/b.txt", "b\n")
    write_text("repo/c.txt", "c\n")

    with pytest.raises(PermissionError):
        mcp_server.findFiles("repo", "missing")  # 탐색 entry 제한 초과 차단
