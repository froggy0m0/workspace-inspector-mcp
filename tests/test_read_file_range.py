import pytest

import workspace_inspector_mcp as mcp_server


# 이 파일은 readFileRange(path, startLine, endLine) MCP tool의 동작만 검증한다.


def test_read_file_range_success(write_bytes):
    """요청한 1-based 줄 범위만 그대로 반환한다."""
    write_bytes("repo/App.java", b"line1\nline2\nline3\nline4\n")

    result = mcp_server.readFileRange("repo/App.java", 2, 3)

    assert result == "line2\nline3\n"


def test_read_file_range_single_line(write_bytes):
    """startLine과 endLine이 같으면 해당 줄 하나만 반환한다."""
    write_bytes("repo/App.java", b"line1\nline2\n")

    result = mcp_server.readFileRange("repo/App.java", 1, 1)

    assert result == "line1\n"


def test_read_file_range_returns_empty_when_start_is_after_eof(write_bytes):
    """시작 줄이 EOF 뒤면 읽을 줄이 없으므로 빈 문자열을 반환한다."""
    write_bytes("repo/App.java", b"line1\n")

    result = mcp_server.readFileRange("repo/App.java", 5, 5)

    assert result == ""


def test_read_file_range_allows_end_after_eof(write_bytes):
    """종료 줄이 EOF를 넘어도 존재하는 요청 범위만 반환한다."""
    write_bytes("repo/App.java", b"line1\nline2\nline3\n")

    result = mcp_server.readFileRange("repo/App.java", 2, 10)

    assert result == "line2\nline3\n"


def test_read_file_range_keeps_last_line_without_newline(write_bytes):
    """마지막 줄에 newline이 없어도 원본 내용 그대로 반환한다."""
    write_bytes("repo/App.java", b"line1\nline2")

    result = mcp_server.readFileRange("repo/App.java", 2, 2)

    assert result == "line2"


def test_read_file_range_replaces_invalid_utf8(write_bytes):
    """깨진 UTF-8 byte는 replacement char로 바꿔서 반환한다."""
    write_bytes("repo/broken.txt", b"line1\nbroken-\xff text\n")

    result = mcp_server.readFileRange("repo/broken.txt", 2, 2)

    assert result == "broken-\ufffd text\n"


def test_read_file_range_blocks_bad_line_range(write_bytes):
    """줄 번호 타입, 시작 줄, 종료 줄, 최대 줄 수 정책을 검증한다."""
    write_bytes("repo/App.java", b"line1\nline2\n")

    with pytest.raises(ValueError):
        mcp_server.readFileRange("repo/App.java", "1", 2)  # 줄 번호는 int여야 한다.

    with pytest.raises(ValueError):
        mcp_server.readFileRange("repo/App.java", 0, 1)  # 시작 줄은 1 이상이어야 한다.

    with pytest.raises(ValueError):
        mcp_server.readFileRange("repo/App.java", 2, 1)  # 종료 줄은 시작 줄보다 작을 수 없다.

    with pytest.raises(ValueError):
        mcp_server.readFileRange("repo/App.java", 1, mcp_server.MAX_RANGE_LINES + 1)  # 한 번에 읽는 줄 수 제한


def test_read_file_range_blocks_bad_path(write_bytes):
    """절대경로, workspace 밖 경로, Windows 경로 문자를 차단한다."""
    write_bytes("repo/App.java", b"line1\n")

    with pytest.raises(PermissionError):
        mcp_server.readFileRange("/tmp/repo/App.java", 1, 1)  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.readFileRange("../repo/App.java", 1, 1)  # workspace 밖 경로 차단

    with pytest.raises(PermissionError):
        mcp_server.readFileRange("C:\\Users\\x", 1, 1)  # Windows 경로 문자 차단


def test_read_file_range_blocks_blocked_dirs(write_text):
    """BLOCKED_DIRS 아래 파일은 존재해도 읽지 않는다."""
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        write_text(f"repo/{blocked_dir}/config.txt", "hidden\n")  # 차단 디렉터리별 파일 생성

        with pytest.raises(PermissionError):
            mcp_server.readFileRange(f"repo/{blocked_dir}/config.txt", 1, 1)  # 차단 디렉터리 접근 차단


def test_read_file_range_blocks_missing_file(workspace_root):
    """workspace 안 경로여도 파일이 없으면 FileNotFoundError를 낸다."""
    with pytest.raises(FileNotFoundError):
        mcp_server.readFileRange("repo/missing.txt", 1, 1)  # 존재하지 않는 파일 차단


def test_read_file_range_blocks_directory_path(workspace_root):
    """readFileRange는 파일 읽기 tool이라 디렉터리 path를 차단한다."""
    (workspace_root / "repo/src").mkdir(parents=True)

    with pytest.raises(IsADirectoryError):
        mcp_server.readFileRange("repo/src", 1, 1)  # 디렉터리 path 차단


def test_read_file_range_blocks_nul_byte(write_bytes):
    """요청 범위 안에 NUL byte가 있으면 바이너리 파일로 보고 차단한다."""
    write_bytes("repo/binary.bin", b"line1\nhello\x00world\n")

    with pytest.raises(PermissionError):
        mcp_server.readFileRange("repo/binary.bin", 2, 2)  # NUL byte 포함 줄 차단
