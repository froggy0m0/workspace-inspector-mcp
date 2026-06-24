from mcp.server.fastmcp import FastMCP

from workspace_file_tools import find_files, list_dir, read_file, read_file_range, search_text
from workspace_git_tools import git_diff, git_log, git_show, git_status


mcp = FastMCP("workspace-inspector")


@mcp.tool()
def readFile(path: str) -> str:
    """
    설정된 workspace root 기준 상대경로의 작은 텍스트 파일 하나를 읽는다.

    메타정보를 붙이지 않고 파일 내용만 반환한다.
    """
    return read_file(path)


@mcp.tool()
def readFileRange(path: str, startLine: int, endLine: int) -> str:
    """
    설정된 workspace root 기준 상대경로의 텍스트 파일 일부 줄 범위를 읽는다.

    메타정보나 줄 번호를 붙이지 않고 요청 범위의 내용만 반환한다.
    """
    return read_file_range(path, startLine, endLine)


@mcp.tool()
def listDir(path: str) -> list[str]:
    """
    설정된 workspace root 기준 상대경로의 디렉터리 목록을 반환한다.

    디렉터리는 이름 뒤에 "/"를 붙인다.
    """
    return list_dir(path)


@mcp.tool()
def findFiles(path: str, pattern: str) -> list[str]:
    """
    설정된 workspace root 기준 상대경로의 디렉터리 아래에서 파일명을 재귀 검색한다.

    파일 내용은 읽지 않고, 파일명에 pattern이 들어간 파일 경로만 반환한다.
    """
    return find_files(path, pattern)


@mcp.tool()
def searchText(path: str, query: str) -> list[str]:
    """
    설정된 workspace root 기준 상대경로의 디렉터리 아래에서 텍스트 내용을 검색한다.

    파일 경로, 줄 번호, 해당 줄을 문자열로 반환한다.
    """
    return search_text(path, query)


@mcp.tool()
def gitStatus(path: str) -> str:
    """
    설정된 workspace root 기준 상대경로의 Git repository 상태를 조회한다.

    git status --short --branch 결과를 그대로 반환한다.
    """
    return git_status(path)


@mcp.tool()
def gitDiff(path: str) -> str:
    """
    설정된 workspace root 기준 상대경로의 Git repository 변경 diff를 조회한다.

    git diff 결과를 그대로 반환한다.
    """
    return git_diff(path)


@mcp.tool()
def gitLog(path: str, limit: int = 30) -> str:
    """
    설정된 workspace root 기준 상대경로의 Git repository commit log를 조회한다.

    limit 기본값은 30, 최대값은 100이다.
    git log --oneline 결과를 그대로 반환하며 HEAD/origin/tag 힌트가 보이면 그대로 유지한다.
    """
    return git_log(path, limit)


@mcp.tool()
def gitShow(path: str, revision: str) -> str:
    """
    설정된 workspace root 기준 상대경로의 Git repository commit 하나를 조회한다.

    revision은 hash, branch, tag, HEAD, <revision>~N 형식만 허용한다.
    git show 결과를 반환하며 range, file, reflog, search, pathspec 문법은 허용하지 않는다.
    """
    return git_show(path, revision)


if __name__ == "__main__":
    mcp.run()
