# rhwp 개발용 뷰어

이 디렉토리는 서드파티 rhwp WASM을 사용하는 저장소 전용 읽기 도구입니다. 뷰어와 WASM·폰트는 HWPX 편집기 배포에 포함되지 않습니다.

저장소 루트에서 실행합니다.

```powershell
python -m viewer.server output/working.hwpx --open
```

출력된 로컬 URL에서 문서를 읽습니다. 편집기가 파일을 저장하면 새 버전을 자동으로 다시 읽습니다. 종료하려면 뷰어 터미널에서 Ctrl+C를 누릅니다.

## 브라우저 검증과 재빌드

서버 테스트는 저장소 루트에서 `python -m unittest discover -s viewer/tests -v`로 실행합니다. 브라우저 통합 검사는 `viewer/tests/browser_smoke.cjs`, `viewer/tests/render_cases.cjs`입니다. 개발용 Node·Playwright·Chrome이 필요하며, 인수로 Playwright 모듈 경로를 지정할 수 있습니다. 제품 실행에는 필요하지 않습니다. 과거 표·그림 시나리오 검증 기록은 로컬 `archive/validation/`에 보관합니다.

재빌드는 Docker를 시작한 뒤 프로젝트 루트에서 `./viewer/build_renderer.ps1`을 실행합니다. 기본 소스 경로는 `vendor/rhwp`이며 HEAD는 반드시 `1a76570e833917d15817415a53c09ad61ab3203f`여야 합니다. 새 환경에서는 다음처럼 선택 체크아웃할 수 있습니다.

```powershell
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/edwardkim/rhwp.git vendor/rhwp
git -C vendor/rhwp sparse-checkout set src crates scripts assets vendor saved tools/rhwp-subsecond bindings/Native tools/batch-convert tools/llm_verifier/verdict_protocol tools/llm_verifier/claim_bind tools/llm_verifier/criteria_decomp rhwp-studio/src
git -C vendor/rhwp checkout 1a76570e833917d15817415a53c09ad61ab3203f
```

위 얕은 clone의 HEAD가 이후 바뀌면 고정 커밋을 별도로 fetch해야 합니다. Windows에서 내려받은 셸 스크립트는 LF 줄바꿈이 필요합니다. 현재 환경에서는 해당 스크립트의 CRLF를 LF로 정규화했습니다. 컨테이너의 Cargo target은 전용 volume에 재사용합니다. 완성한 JS/WASM의 SHA-256과 고정 커밋은 `viewer/web/rhwp/provenance.json`에 기록합니다.

[서드파티 고지](../THIRD_PARTY_NOTICES.md)
