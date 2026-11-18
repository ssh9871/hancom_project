# HWPX CLI + MCP

HWPX를 편집하는 Python CLI와 로컬 MCP 서버입니다. **개발 중이며 계획 전체가 완료된 버전은 아닙니다.** 사용법은 아래 예시와 [편집 연산 목록](hwpx_cli/operations.md)을 참조하세요. 보고서·연구 자료인 `docs/`와 `archive/`는 로컬에 보관하며 저장소에는 포함하지 않습니다.

## 처음 설치하기 (Windows PowerShell)

Git, Python 3.11 이상, 의존성을 내려받을 인터넷 연결이 필요합니다. 한컴·Rust·Docker·Node는 CLI/MCP 실행에 필요하지 않습니다. 아래 명령은 빈 작업 폴더에서 시작합니다. 이미 클론했다면 `cd hancom_project` 이후부터 실행하세요.

```powershell
git clone https://github.com/ssh9871/hancom_project.git
cd hancom_project
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[mcp]"
# 가상환경 활성화 스크립트 없이도 같은 Python과 hwpx를 사용합니다.
$env:PATH = "$(Join-Path $PWD '.venv/Scripts');$env:PATH"
hwpx --help
hwpx operations
```

MCP가 필요 없으면 설치 인수를 `.`으로 바꿉니다. 위 명령은 전역 Python 패키지를 사용하지 않는 가상환경을 만듭니다. 이후 명령은 **저장소 루트와 같은 PowerShell 세션**에서 실행합니다. 새 터미널에서는 PATH 설정을 다시 하거나 `hwpx` 대신 `.\.venv\Scripts\python.exe -m hwpx_cli`를 사용하세요. Linux/macOS에서는 `python3 -m venv .venv`, `.venv/bin/python -m pip install ".[mcp]"` 후 가상환경을 활성화하면 같은 CLI를 사용할 수 있습니다. 아래 `$변수` 구문은 PowerShell용입니다.

`docs/`, `archive/`, `vendor/rhwp/`는 클론에 없어도 됩니다. 아래 실습에 필요한 JSON·이미지·뷰어 WASM·폰트는 모두 저장소에 포함되어 있습니다. Python 패키지 설치만으로 뷰어·실습 자료가 설치되지는 않으므로, 뷰어와 실습은 클론한 저장소에서 실행합니다.

## 작동 원리

`명령 해석 → ZIP/XML 패키지 열기 → 메모리 편집 → 구조 검증 → 저장`

1. [CLI](hwpx_cli/cli.py)의 `text`는 옵션을 편집 연산으로 변환하고, `apply`는 JSON 연산을 읽습니다. MCP도 같은 편집·저장 코드를 호출합니다.
2. [패키지 처리기](hwpx_cli/package.py)는 HWPX ZIP의 `Contents/content.hpf`에서 manifest와 spine을 읽습니다. 본문은 섹션 XML, 공유 서식은 `header.xml`, 이미지 등은 `BinData/`에 있습니다.
3. 편집 대상은 `XML 경로#자식 인덱스` 주소로 찾습니다. [텍스트 편집기](hwpx_cli/editing.py)는 run과 텍스트를 수정하고, 수정된 문단의 줄 배치 캐시를 제거합니다. 수정하지 않은 ZIP 항목의 내용 바이트는 유지합니다.
4. 배치 전체를 메모리에서 처리한 후 서식·리소스 참조와 표 격자를 검증합니다. 실패하면 배치를 저장하지 않습니다. [저장 코드](hwpx_cli/storage.py)는 제자리 저장 시 잠금·버전 확인과 임시 파일 교체를 사용하며, SQLite 스냅샷으로 Undo/Redo를 제공합니다.

## CLI 명령어 모음

아래 명령 앞에는 `hwpx`를 붙입니다. 옵션은 `hwpx <명령> --help`로 확인하고, JSON 인수는 [편집 연산 목록](hwpx_cli/operations.md)에서 확인합니다. `operations`는 연산 **이름**을 출력합니다.

| 명령 | 하는 일 |
|---|---|
| `create --output <결과.hwpx>` | 빈 문서 생성. `--template <원본.hwpx>`로 양식 복제 가능 |
| `inspect <문서.hwpx>` | 구조·문단·표·개체 주소와 파일 버전 조회 |
| `find <문서.hwpx> --text <검색어>` | 문단 주소와 문자 범위 조회 |
| `validate <문서.hwpx>` | 패키지 구조·참조 검사 |
| `copy <문서.hwpx> --output <결과.hwpx>` | 새 경로에 복사 |
| `text insert <문서.hwpx> --target <주소> --start 0 --text <문구> --in-place` | 텍스트 삽입 |
| `text replace <문서.hwpx> --text <기존> --with <변경> --in-place` | 치환. 여러 건은 `--all`, 특정 문단은 `--target` |
| `text delete <문서.hwpx> --target <주소> --start 0 --end 2 --in-place` | 문자 범위 삭제 |
| `apply <문서.hwpx> --batch <배치.json> --in-place` | UTF-8 JSON 배열의 연산 1~1,000개를 순서대로 적용 |
| `apply <문서.hwpx> --operation <JSON객체> --in-place` | JSON 객체 한 개 적용. 셸 인용 문제를 피하려면 `--batch` 권장 |
| `operations` | 구현된 JSON 연산 이름 조회 |
| `history <문서.hwpx> list/undo/redo` | 저장 이력 조회·이전/다음 저장본 복원 |
| `history <문서.hwpx> restore/prune --revision <ID>` | 특정 수정본 복원/이전 이력 정리 |
| `password set/change/remove <문서.hwpx> --output <결과.hwpx>` | 터미널 암호 입력으로 설정·변경·제거 |
| `mcp --workspace <폴더>` | 선택 의존성 설치 후 stdio MCP 서버 실행 |

`text`와 `apply`는 `--in-place` 대신 `--output <새.hwpx>`를 사용할 수 있습니다. 기존 출력 파일은 덮어쓰지 않습니다. `--expect-version <SHA-256>`으로 조회 이후 변경된 문서의 편집을 거부할 수 있습니다. 성공 결과는 stdout JSON, 오류는 stderr JSON과 종료 코드 2로 확인합니다.

## MCP로 에이전트 연결

이 서버는 **로컬 stdio MCP를 지원하는 에이전트**에서 사용할 수 있습니다. 아래 공통 준비 후 사용하는 클라이언트의 등록 방법 하나를 선택하세요.

### 공통 준비

프로젝트 폴더에서 MCP 옵션을 설치하고 Python·작업 폴더의 절대 경로를 구합니다. 가상환경을 활성화하지 않아도 됩니다.

```powershell
$hwpxPython = (Resolve-Path .venv/Scripts/python.exe).Path
& $hwpxPython -m pip install ".[mcp]"
$hwpxWorkspace = (Get-Location).Path
```

`--workspace`는 문서와 삽입할 이미지 경로의 기준이자 접근 가능한 폴더입니다. 해당 폴더 안의 상대 경로와 절대 경로를 사용할 수 있습니다. Linux/macOS에서는 `.venv/bin/python`의 절대 경로를 사용합니다. 비밀번호로 보호된 문서는 대화형 CLI로 편집합니다.

### Codex CLI

Codex CLI가 설치된 환경에서 공통 준비와 같은 PowerShell 세션으로 실행합니다.

```powershell
codex mcp add hwpx -- $hwpxPython -m hwpx_cli mcp --workspace $hwpxWorkspace
codex mcp list
```

### Claude Code

Claude Code가 설치된 환경에서 공통 준비와 같은 PowerShell 세션으로 실행합니다. 아래 설정은 현재 프로젝트에서만 사용하는 개인 설정(`local` 범위)입니다.

```powershell
claude mcp add --transport stdio --scope local hwpx -- $hwpxPython -m hwpx_cli mcp --workspace $hwpxWorkspace
claude mcp list
claude mcp get hwpx
```

Claude Code에서 프로젝트를 연 뒤 `/mcp`로 연결 상태를 확인합니다. 등록 구문과 범위는 [Claude Code 공식 MCP 문서](https://code.claude.com/docs/en/mcp)를 참조하세요.

### 다른 에이전트의 공통 설정

클라이언트의 MCP 설정 화면·설정 파일에서 다음 값을 지정합니다. `--workspace`만으로 Python 모듈 설치 경로가 바뀌지는 않으므로, 반드시 위에서 패키지를 설치한 Python을 사용하세요.

| 설정 | 값 |
|---|---|
| 서버 이름 | `hwpx` |
| 전송 방식 | `stdio` (로컬 명령 실행) |
| 실행 파일 / command | 가상환경의 Python 절대 경로 |
| 인수 / args | `-m`, `hwpx_cli`, `mcp`, `--workspace`, 문서 작업 폴더의 절대 경로 |

`mcpServers` 형식을 사용하는 클라이언트의 JSON 예시입니다. 두 경로를 자신의 실제 경로로 바꾸고 기존 서버 설정에 병합하세요. JSON의 `args`는 각 인수를 별도 문자열로 작성하며, 공백이 있는 경로에도 추가 따옴표를 넣지 않습니다.

```json
{
  "mcpServers": {
    "hwpx": {
      "command": "C:/work/hancom_project/.venv/Scripts/python.exe",
      "args": [
        "-m", "hwpx_cli", "mcp", "--workspace",
        "C:/work/hancom_project"
      ]
    }
  }
}
```

설정 파일 위치와 최상위 키는 클라이언트마다 다르므로 해당 제품의 MCP 문서를 따릅니다. 예를 들어 [Cursor 공식 MCP 문서](https://prod.cursor.com/docs/mcp)는 `mcp.json`의 `mcpServers` 설정을 안내합니다. 현재 서버에는 HTTP/SSE 엔드포인트가 없으므로 원격 URL만 받는 클라이언트에는 그대로 연결할 수 없습니다. 원격 실행 환경에서는 그 환경에 Python·패키지·작업 파일을 준비해야 하며, 이 컴퓨터의 `C:/...` 경로를 그대로 사용할 수 없습니다.

등록 후 클라이언트에서 서버 도구를 다시 불러오고 `hwpx_operations`를 호출해 연결을 확인하세요. 클라이언트가 서버 프로세스를 실행·관리하므로 별도 터미널에서 서버를 미리 띄울 필요는 없습니다. 직접 실행했을 때는 stdio 요청을 기다리며 출력 없이 대기하는 것이 정상입니다. Claude Code·Cursor의 제품별 실제 연결은 별도로 검증하지 않았으며, 이 저장소의 MCP 테스트는 표준 stdio 클라이언트로 수행합니다.

### 제공 도구와 편집 흐름

| MCP 도구 | 용도 |
|---|---|
| `hwpx_create` | `output` 경로에 빈 HWPX 생성 |
| `hwpx_replace` | 여러 문구를 한 번에 찾아 치환하고 저장·검증 |
| `hwpx_inspect` | 문단·표·개체 주소와 문서 버전 조회. `kind` 또는 `target`으로 범위 지정 |
| `hwpx_find` | `text`로 검색하고 대상 주소와 텍스트 범위 조회 |
| `hwpx_operations` | `family`로 `table`, `image`, `format` 등의 [연산과 JSON 인수](hwpx_cli/operations.md) 조회 |
| `hwpx_apply` | 조회한 버전과 `operations`로 편집 후 저장 |
| `hwpx_validate` | 저장한 HWPX의 구조 확인 |

에이전트에 “`output/working.hwpx`에서 ‘초안’을 모두 ‘최종안’으로 바꾸고 `output/final.hwpx`로 저장해 줘”라고 요청하면 `hwpx_replace`가 한 번의 호출로 처리할 수 있습니다. `replacements`에 `[{"text":"초안","replacement":"최종안"}]`을 전달하면 치환한 개수와 저장본의 검증 결과가 반환됩니다. 하나라도 일치하는 문구가 없으면 전체 배치가 취소됩니다. 길이가 같은 치환은 글자 위치마다 기존 서식 구간을 보존합니다.

특정 위치를 편집할 때는 `hwpx_find` 또는 `hwpx_inspect`의 `version`을 `hwpx_apply`의 `expected_version`으로 전달합니다. 조회는 기본 15개씩 반환하며 `next_offset`이 숫자면 다음 `offset`으로 전달합니다. `hwpx_inspect` 기본 모드는 문단 텍스트를 160자로 제한합니다. 정확한 전문과 XML 속성이 필요하면 해당 `target`을 지정하고 `detail: "full"`로 조회합니다.

`output`은 새 파일 경로이며, 현재 작업 파일을 갱신하려면 `in_place: true`를 지정합니다. 제자리 저장은 CLI의 `history`에서 되돌릴 수 있습니다.

## 편집 실습: 생성부터 표·그림·Undo/Redo까지

로컬 보고서의 실습 명령과 배치를 저장소만으로 실행할 수 있게 옮겼습니다. 아래 블록을 **위에서부터 순서대로** 실행하세요. 매번 새 출력 폴더를 만들므로 반복 실행해도 이전 결과를 덮어쓰지 않습니다. 주소는 이 실습에서 생성한 문서 전용이며 다른 문서에서는 `inspect/find` 결과를 사용합니다.

<!-- walkthrough:start -->
```powershell
$lab = 'examples/walkthrough'
$run = "output/walkthrough-$([guid]::NewGuid().ToString('N'))"
$work = "$run/work.hwpx"

# 준비: 제목과 표·그림을 넣을 빈 문단 두 개
hwpx create --output $work
hwpx text insert $work --target 'Contents/section0.xml#0' --start 0 --text '환경 캠페인 초안' --in-place
hwpx apply $work --batch "$lab/00-setup.json" --in-place

# 1. 텍스트 검색·치환: 초안 → 실행안
hwpx find $work --text '초안'
hwpx text replace $work --target 'Contents/section0.xml#0' --text '초안' --with '실행안' --in-place
# 2. 제목을 24pt·굵은 파랑으로 변경
hwpx apply $work --batch "$lab/02-format.json" --in-place
# 3. 설명 문단 추가 (뒤의 문단 주소가 이동)
hwpx apply $work --batch "$lab/03-paragraph.json" --in-place
# 4. 2행 2열 표와 테두리 생성
hwpx apply $work --batch "$lab/04-table.json" --in-place
hwpx inspect $work
# 5. 표 맨 아래 빈 행 추가 → 3행 2열
hwpx apply $work --batch "$lab/05-row.json" --in-place
# 6. 저장소의 무궁화 WEBP를 50 × 32.8mm로 삽입
hwpx apply $work --batch "$lab/06-image.json" --in-place
# 7. 그림 삽입 취소·재실행과 구조 검증
hwpx history $work undo
hwpx history $work redo
hwpx validate $work
hwpx find $work --text '실행안'

# 8. 별도 문서: 좌우 여백 18mm, 가운데 정렬, 3부터 번호 매기기
$advanced = "$run/advanced.hwpx"
hwpx create --output $advanced
hwpx apply $advanced --batch "$lab/08-layout-setup.json" --in-place
hwpx apply $advanced --batch "$lab/08-layout.json" --in-place
# 9. 2행 3열 표의 첫 행에서 SUM(A1:B1) → 세 번째 셀에 30 기록
hwpx apply $advanced --batch "$lab/09-table-calculate.json" --in-place
hwpx find $advanced --text '30'
# 10. 셀 병합·전치·120 × 36mm로 크기 변경
hwpx apply $advanced --batch "$lab/10-table-structure.json" --in-place
# 사본에서 병합 해제도 확인
$unmerged = "$run/unmerged.hwpx"
hwpx copy $advanced --output $unmerged
hwpx apply $unmerged --batch "$lab/10-table-unmerge.json" --in-place
hwpx validate $unmerged
# 11. 머리말·각주·책갈피·필드·수식·사각형 추가
hwpx apply $advanced --batch "$lab/11-controls-shape.json" --in-place
hwpx find $advanced --text '운영팀'
# 12. 스타일 적용·HTML 붙여넣기·문단 복제
hwpx apply $advanced --batch "$lab/12-style-html.json" --in-place
hwpx find $advanced --text '현장 집계'
hwpx find $advanced --text '이어서 확인'
hwpx validate $advanced
# 13. 사본 보관 후 이력 조회·리비전 3으로 복원
hwpx copy $advanced --output "$run/advanced-final.hwpx"
hwpx history $advanced list
hwpx history $advanced restore --revision 3
hwpx validate $advanced
```
<!-- walkthrough:end -->

정상 결과는 각 명령의 종료 코드 0, `validate`의 `valid: true`입니다. `$work`에는 `환경 캠페인 실행안`, 설명 문단, 3행 2열 표와 그림이 있습니다. `$run/advanced-final.hwpx`에는 전치된 3행 2열 표·운영팀 필드·수식·도형·HTML 문단이 남습니다. `현장 집계`는 복제로 두 번 검색됩니다. 복원한 `$advanced`에서는 표·도형이 사라지고 제목과 번호 문단으로 돌아갑니다.

화면은 다음 명령으로 확인할 수 있습니다. 뷰어는 읽기 전용이며 별도 터미널에서 실행합니다. 브라우저가 열리면 편집 후 저장한 내용을 자동으로 다시 읽습니다. 서버 종료는 Ctrl+C입니다.

```powershell
.\.venv\Scripts\python.exe -m viewer.server $work --open
```

다른 터미널에서는 `$work` 변수 대신 출력된 실제 HWPX 경로를 넣으세요. 뷰어가 출력하는 URL에는 접근 토큰이 있으므로 로컬 브라우저에서 그대로 사용합니다.

## 텍스트 편집과 대상 선택

별도 예제입니다. `output/working.hwpx`가 없는 상태에서 시작합니다. 이미 있다면 새 파일명을 사용하세요.

```powershell
python -m hwpx_cli create --output output/working.hwpx
python -m hwpx_cli inspect output/working.hwpx --json
python -m hwpx_cli text insert output/working.hwpx --target 'Contents/section0.xml#0' --start 0 --text '안녕하세요' --in-place
python -m hwpx_cli find output/working.hwpx --text '안녕하세요' --json
python -m hwpx_cli text replace output/working.hwpx --text '안녕하세요' --with '반갑습니다' --in-place
python -m hwpx_cli history output/working.hwpx list
python -m hwpx_cli history output/working.hwpx undo
python -m hwpx_cli history output/working.hwpx redo
```

- 주소는 `inspect/find` 결과를 사용합니다. `#` 뒤는 XML의 자식 인덱스 경로입니다. 본문뿐 아니라 표 셀·각주·머리말 내부 문단도 개별 주소로 선택합니다.
- 텍스트 범위는 0부터 시작하는 Python 코드 포인트 기준 `[start,end)`입니다. 이모지는 UTF-16 코드 유닛 수로 세지 않습니다. 문단 나눔은 텍스트 줄바꿈과 다른 연산입니다.
- 구조를 바꾸면 주소를 다시 조회하세요. `--expect-version`에 조회 결과의 SHA-256을 전달하면 다른 버전의 주소 사용을 방지합니다. 배치 내부 주소는 각 앞선 연산 이후의 XML 구조 기준입니다.
- 기본 저장은 새 경로 `--output`이며 기존 파일을 거부합니다. `--in-place`를 지정한 경우에만 원본 작업 파일을 교체합니다. 원본 연구 샘플은 복사해서 편집하세요.
- 결과는 JSON, 오류는 stderr JSON, 실패 종료 코드는 2입니다. 검색 다중 일치 치환은 `--all`을 명시해야 합니다.

## JSON 연산과 배치

PowerShell의 JSON 인수 인용 차이를 피하려면 UTF-8 JSON 파일을 권장합니다. 예를 들어 `operations.json`을 다음과 같이 작성합니다.

```json
[
  {"op":"text.range","target":"Contents/section0.xml#0","start":0,"end":0,"value":"문서 제목\n본문"},
  {"op":"format.text","target":"Contents/section0.xml#0","start":0,"end":5,"properties":{"size":20,"bold":true,"color":"#2463A6"}},
  {"op":"paragraph.insert-after","target":"Contents/section0.xml#0","text":""},
  {"op":"table.create","target":"Contents/section0.xml#1","rows":2,"cols":3,"values":[["항목","수량","금액"],["예시","2","1000"]],"width":160,"row_height":10}
]
```

```powershell
python -m hwpx_cli create --output output/batch.hwpx
python -m hwpx_cli apply output/batch.hwpx --batch operations.json --in-place
```

각 배치는 검증 후 한 번에 저장하며 Undo 한 번으로 복원합니다. 실패한 배치는 파일에 부분 저장되지 않습니다. 파일 경로가 상대경로이면 명령을 실행한 폴더 기준입니다.

연산별 인수와 단위는 [HWPX 편집 연산](hwpx_cli/operations.md)을 참조하세요.

## 암호 문서

```powershell
python -m hwpx_cli password set output/working.hwpx --output output/protected.hwpx
python -m hwpx_cli inspect output/protected.hwpx
python -m hwpx_cli password change output/protected.hwpx --output output/new-password.hwpx
python -m hwpx_cli password remove output/protected.hwpx --output output/unprotected.hwpx
```

비밀번호는 숨김 입력으로 받으며 명령 인수로 받지 않습니다. 암호 문서의 일반 편집·Undo/Redo는 같은 암호로 처리합니다. 암호 전환은 **새 파일로만 출력**하여 과거 평문 기록·다른 암호의 기록이 현재 파일의 히스토리에 섞이지 않게 합니다. 기존 파일·백업은 자동 삭제하지 않습니다. 지원 규약은 rhwp 고정 버전의 ODF AES-256-CBC/SHA-256/PBKDF2 계약이며 전자서명 문서 편집은 거부합니다.

## 히스토리와 보존

작업 파일 옆 `.hwpx-history/`의 SQLite에 명령·스냅샷을 저장하고 첫 제자리 편집 전 `<파일>.hwpx.bak`을 만듭니다. 일반 문서의 스냅샷도 문서 내용을 포함하므로 파일과 함께 관리하세요. 암호 문서의 스냅샷은 암호화 바이트입니다.

`history <파일> list`에서 용량을 확인하고 `history <파일> prune --revision N`으로 N 이전 버전을 정리합니다. 정리된 버전은 복원할 수 없습니다. 현재 자동 보관 한도는 없으므로 장시간 사용 시 직접 정리해야 합니다. 프로세스 중단 후 남은 `.hwpx-lock`은 다른 쓰기 작업이 없는지 확인한 뒤 제거하세요. 그다음 명령이 트랜잭션 기록을 대조해 복구합니다.

수정하지 않은 ZIP 항목 내용은 유지하며 수정 XML은 재직렬화합니다. 전체 압축 파일 바이트 동일성·모든 한컴 조판·전자서명 유지는 보장하지 않습니다.

## 개발 디렉토리

| 경로 | 역할 |
|---|---|
| `hwpx_cli/` | 배포하는 CLI, HWPX 편집·저장 코드, MCP 서버 |
| `tests/` | 편집기·MCP 회귀 테스트, `integration/`의 CLI 검사, `fixtures/`의 입력 HWPX·이미지·배치 |
| [viewer/](viewer/README.md) | 저장소에서 별도로 실행하는 읽기 전용 rhwp 뷰어와 재빌드 도구 |
| `examples/` | 사용자용 배치 예제 |
| `docs/` | 보고서·편집 실습 자료. 로컬 보관, Git 제외 |
| `vendor/rhwp/` | 렌더러 재빌드에 쓰는 로컬 rhwp 체크아웃 |
| `archive/` | 연구·실험·검증 기록과 이전 생성 결과. 로컬 보관, Git 제외 |
| `output/` | 실습 및 검증 실행에서 생성된 문서와 로그 |

제품 코드·개발 스크립트·테스트 데이터의 구분은 [ArtCraft 디렉토리 구성](https://github.com/storytold/artcraft)을 참고했습니다. 이전 실행 결과는 로컬 `archive/validation/`과 `archive/output-before-git/`에 있습니다.

`archive/experiments/`의 초기 스크립트와 `archive/research/`의 기록에는 당시 파일명과 실행 경로가 남아 있습니다. 현재 CLI 검증은 `tests/integration/`, 뷰어 검증은 `viewer/tests/`에서 실행합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s viewer/tests -v
# 매번 존재하지 않는 출력 폴더를 인수로 지정합니다.
.\.venv\Scripts\python.exe tests/integration/spec_cli_check.py "output/spec-$([guid]::NewGuid().ToString('N'))"
```

MCP 선택 의존성 없이 설치하면 MCP 테스트는 건너뜁니다. 브라우저 렌더링·한컴 재열기 검증은 위 테스트에 포함되지 않습니다.

## 에이전트 작업 순서와 제한

처음 작업하는 에이전트는 [AGENTS.md](AGENTS.md)를 읽고 설치 → `inspect/find` → 연산 선택 → 새 경로 저장 → `validate` 순서로 진행합니다. 작업 파일의 주소·서식 ID를 다른 문서에 재사용하지 마세요.

- 입력은 `.hwpx`입니다. 바이너리 `.hwp`와 전자서명 문서 편집은 지원하지 않습니다.
- 문단 간 텍스트 범위, 필드·책갈피/개체 경계를 가로지르는 일부 편집은 거부합니다. 구조 변경 후 주소를 다시 조회하세요.
- 수식 크기는 직접 지정하며, 표 계산 결과는 한 번 기록합니다. 자동 재계산·모든 한컴 수식 의미 일치는 보장하지 않습니다.
- 미리보기 텍스트·썸네일은 갱신하지 않습니다. 구조 검증 성공은 한컴과 동일한 조판을 보장하지 않으므로 최종 문서는 뷰어와 실제 사용할 편집기에서 확인하세요.
- `No module named ...`는 위 가상환경 Python으로 재설치하고, `hwpx`를 찾지 못하면 PATH 설정 또는 가상환경 Python의 `-m hwpx_cli`를 사용하세요. 출력 파일이 존재한다는 오류는 새 출력 경로로 해결합니다. 편집 거부 오류가 나면 저장 여부를 확인하고 `inspect/find`로 다시 조회하세요.

서드파티 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참조하세요.
