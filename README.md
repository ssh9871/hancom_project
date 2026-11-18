# HWPX CLI + MCP

HWPX를 편집하는 Python CLI와 로컬 MCP 서버입니다. **개발 중이며 계획 전체가 완료된 버전은 아닙니다.** 사용법은 아래 예시와 [편집 연산 목록](hwpx_cli/operations.md)을 참조하세요. 보고서·연구 자료인 `docs/`와 `archive/`는 로컬에 보관하며 저장소에는 포함하지 않습니다.

## 실행

Python 3.11 이상이 필요합니다. 프로젝트 폴더에서 가상환경을 만들고 의존성을 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
```

의존성이 설치되어 있으면 프로젝트 폴더에서 다음 명령으로 실행할 수 있습니다.

```powershell
python -m hwpx_cli --help
python -m hwpx_cli operations
python -m hwpx_cli create --output output/working.hwpx
```


패키지 설치가 필요하면 가상환경에서 `python -m pip install .`을 사용합니다. 설치 시 Python 의존성이 없으면 다운로드가 필요합니다.

## MCP로 에이전트 연결

프로젝트 폴더에서 MCP 옵션을 설치하고 Codex에 로컬 서버를 등록합니다.

```powershell
python -m pip install ".[mcp]"
$python = (Get-Command python).Source
codex mcp add hwpx -- $python -m hwpx_cli mcp --workspace (Get-Location).Path
codex mcp list
```

다른 MCP 클라이언트에서도 같은 실행 파일과 인수를 stdio 서버로 등록할 수 있습니다. `--workspace`는 문서와 삽입할 이미지 경로의 기준 폴더입니다. 등록한 폴더 안에서 상대 경로와 절대 경로를 사용할 수 있습니다. 비밀번호로 보호된 문서는 대화형 CLI로 편집합니다.

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

## 텍스트 편집과 대상 선택

```powershell
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
python -m unittest discover -s tests -v
```

서드파티 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참조하세요.
