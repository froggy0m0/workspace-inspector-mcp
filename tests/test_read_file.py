import pytest

import workspace_inspector_mcp as mcp_server


# 이 파일은 readFile(path) MCP tool의 동작만 검증한다.


def test_read_file_success(write_bytes):
    """작은 텍스트 파일 내용을 그대로 반환한다."""
    write_bytes("repo/README.md", b"hello\n")

    result = mcp_server.readFile("repo/README.md")

    assert result == "hello\n"


def test_read_file_replaces_invalid_utf8(write_bytes):
    """깨진 UTF-8 byte는 replacement char로 바꿔서 반환한다."""
    write_bytes("repo/broken.txt", b"broken-\xff text\n")

    result = mcp_server.readFile("repo/broken.txt")

    assert result == "broken-\ufffd text\n"


def test_read_file_blocks_empty_path():
    """빈 path와 공백 path는 읽을 대상이 없으므로 차단한다."""
    with pytest.raises(PermissionError):
        mcp_server.readFile("")  # 빈 path 차단

    with pytest.raises(PermissionError):
        mcp_server.readFile("   ")  # 공백만 있는 path 차단


def test_read_file_blocks_bad_path(write_text):
    """절대경로, workspace 밖 경로, Windows 경로 문자를 차단한다."""
    write_text("repo/README.md", "hello\n")

    with pytest.raises(PermissionError):
        mcp_server.readFile("/tmp/repo/README.md")  # 절대경로 차단

    with pytest.raises(PermissionError):
        mcp_server.readFile("../repo/README.md")  # workspace 밖 경로 차단

    with pytest.raises(PermissionError):
        mcp_server.readFile("C:\\Users\\x")  # Windows 경로 문자 차단


def test_read_file_blocks_blocked_dirs(write_text):
    """BLOCKED_DIRS 아래 파일은 존재해도 읽지 않는다."""
    for blocked_dir in sorted(mcp_server.BLOCKED_DIRS):
        write_text(f"repo/{blocked_dir}/config.txt", "hidden\n")  # 차단 디렉터리별 파일 생성

        with pytest.raises(PermissionError):
            mcp_server.readFile(f"repo/{blocked_dir}/config.txt")  # 차단 디렉터리 접근 차단


def test_read_file_blocks_missing_file(workspace_root):
    """workspace 안 경로여도 파일이 없으면 FileNotFoundError를 낸다."""
    with pytest.raises(FileNotFoundError):
        mcp_server.readFile("repo/missing.txt")  # 존재하지 않는 파일 차단


def test_read_file_blocks_directory_path(workspace_root):
    """readFile은 파일 읽기 tool이라 디렉터리 path를 차단한다."""
    (workspace_root / "repo/src").mkdir(parents=True)

    with pytest.raises(IsADirectoryError):
        mcp_server.readFile("repo/src")  # 디렉터리 path 차단


def test_read_file_blocks_large_file(write_bytes):
    """MAX_READ_BYTES를 넘는 파일은 너무 큰 파일로 보고 차단한다."""
    write_bytes("repo/large.txt", b"a" * (mcp_server.MAX_READ_BYTES + 1))

    with pytest.raises(PermissionError):
        mcp_server.readFile("repo/large.txt")  # 파일 크기 제한 초과 차단


def test_read_file_blocks_nul_byte(write_bytes):
    """NUL byte가 하나라도 있으면 바이너리 파일로 보고 차단한다."""
    write_bytes("repo/binary.bin", b"hello\x00world\n")

    with pytest.raises(PermissionError):
        mcp_server.readFile("repo/binary.bin")  # NUL byte 포함 파일 차단
