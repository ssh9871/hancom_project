# HWPX CLI 작업 안내

이 저장소는 Python 3.11+ 기반 HWPX ZIP/XML 편집 CLI와 선택 MCP 서버, 읽기 전용 뷰어다. 처음에는 README.md의 설치·작동 원리·명령어 표·편집 실습을 읽는다. 연산 인수는 hwpx_cli/operations.md에서 확인한다.

- 저장소 루트에서 `python -m venv .venv` 후 Windows는 `.venv/Scripts/python.exe -m pip install ".[mcp]"`, Linux/macOS는 `.venv/bin/python -m pip install ".[mcp]"`로 설치한다. 전역 패키지에 의존하지 않는다.
- 활성화 없이 Windows는 `.venv/Scripts/python.exe -m hwpx_cli`, Linux/macOS는 `.venv/bin/python -m hwpx_cli`로 실행할 수 있다. 아래 `hwpx`는 이 명령의 약칭이다.
- 편집 전 `hwpx inspect <파일>` 또는 `hwpx find <파일> --text <문구>`로 실제 target과 version을 얻는다. 실제 문서에 실습의 target·서식 ID를 그대로 쓰지 않는다.
- 원본 보존을 기본으로 `--output <새.hwpx>`를 사용한다. 제자리 편집이 요청된 경우 `--in-place`와 조회한 `--expect-version`을 사용한다. 구조 변경 후 target을 다시 조회한다.
- 배치는 UTF-8 JSON 배열(1~1,000개)로 저장해 `apply --batch`에 전달한다. 상대 경로는 실행 폴더 기준이며 JSON 안 이미지 경로도 같다. 하나가 실패하면 배치는 저장되지 않는다. 실패를 무시하거나 XML을 임의 주입하여 우회하지 않는다.
- 저장 후 `validate`, `find/inspect`로 구조와 요청 내용 모두 확인한다. 결과 파일 경로와 검증 범위를 사용자에게 알린다. 구조 검증과 화면 조판 검증을 구별한다.
- 암호는 대화형 CLI 프롬프트로만 입력한다. MCP는 암호 문서 편집을 지원하지 않는다. 비밀번호를 명령·배치·로그·커밋에 넣지 않는다.
- `docs/`, `archive/`, `vendor/rhwp/`는 로컬 전용이며 없어도 설치·실습·테스트가 동작해야 한다. 새 생성물은 Git에서 제외된 `output/`에 둔다. 원본·백업·히스토리를 허락 없이 삭제하지 않는다.
- 뷰어는 저장소에서 `python -m viewer.server <파일> --open`으로 실행한다. 포함된 WASM·폰트로 실행 가능하며 Rust/Docker는 렌더러를 재빌드할 때만 필요하다.
- 변경 검증은 가상환경 Python으로 `-m unittest discover -s tests -v`, `-m unittest discover -s viewer/tests -v`를 실행한다. 넓은 CLI 통합 검사는 `tests/integration/spec_cli_check.py <새 출력폴더>`다. MCP 테스트를 포함하려면 `.[mcp]`가 필요하다.
