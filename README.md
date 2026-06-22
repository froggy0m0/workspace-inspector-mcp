# workspace-inspector-mcp

지정한 workspace 안의 파일과 폴더를 안전하게 조회하는 MCP 서버입니다.

`WORKSPACE_INSPECTOR_ROOT` 환경변수로 workspace root를 지정하며, 모든 tool은 이 root 하위 경로만 읽습니다.

## 기능

### 파일 조회

| tool | 용도 |
| --- | --- |
| `readFile(path)` | 파일 전체 읽기 |
| `readFileRange(path, startLine, endLine)` | 파일 일부 줄 읽기 |
| `listDir(path)` | 폴더 목록 보기 |
| `findFiles(path, pattern)` | 파일명 검색 |
| `searchText(path, query)` | 파일 내용 검색 |

### Git 조회

| tool | 용도 |
| --- | --- |
| `gitStatus(path)` | git status 조회 |
| `gitDiff(path)` | git diff 조회 |

## 차단 정책

### 공통

- 절대경로 차단
- Windows/UNC 경로 문자 차단: `\`, `:`
- workspace root 밖 경로 차단

### 파일 조회

- `.git`, `.agents`, `.codex`, `.idea` 차단
- symlink 탐색 차단
- `readFile`: 1MB 초과, NUL byte 포함 파일 차단
- `readFileRange`: 최대 300줄
- `findFiles`: 결과 최대 500개, 탐색 최대 50,000개
- `searchText`: 결과 최대 200줄

### Git 조회

- 디렉터리 path만 허용
- Git work tree가 아니면 차단
- Git repository root가 workspace root 밖이면 차단
- `gitStatus`: `git status --short --branch` 결과 반환
- `gitDiff`: `git diff --no-ext-diff --no-textconv` 결과를 반환하며, UTF-8 출력이 500,000 bytes를 초과하면 차단

## 환경변수

```bash
export WORKSPACE_INSPECTOR_ROOT="<workspace-root>"
```

## 테스트

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```
