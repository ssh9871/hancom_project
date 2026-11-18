# 서드파티 고지

## rhwp

- 원본: https://github.com/edwardkim/rhwp
- 고정 커밋: `1a76570e833917d15817415a53c09ad61ab3203f`
- 라이선스: MIT, Copyright (c) 2025–2026 Edward Kim.
- 별도 개발용 뷰어에 보관한 파일: WASM·JS·타입 선언, 원본 MIT LICENSE 및 의존성 고지.
- 파일: `viewer/web/rhwp/LICENSE`, `THIRD_PARTY_LICENSES.md`, `provenance.json`.
- 암호 처리와 XML 구성은 해당 고정 소스의 계약을 참고하여 Python으로 구현했다. rhwp 편집·저장 API는 호출하지 않는다.

## 폰트

Noto Sans KR Regular/Bold, Noto Serif KR Regular은 rhwp의 `assets/fonts`에 있는 원본 파일을 변경 없이 `viewer/`에 보관한다. Adobe/Google의 SIL Open Font License 1.1을 따른다. 폰트 메타데이터의 저작권은 `(c) 2014–2021 Adobe (http://www.adobe.com/), with Reserved Font Name 'Source'.`이다. 같은 계열 원본 고지와 OFL 본문은 `viewer/web/fonts/SourceHanSerifK-OFL.txt`에 포함한다. 시스템의 한컴·Microsoft 폰트는 복사하거나 배포하지 않는다.

## Python과 개발 도구

- lxml: BSD 계열. libxml2/libxslt 고지는 해당 배포 패키지 참조.
- Pillow: HPND 계열. 포함 코덱의 고지는 Pillow 배포 패키지 참조.
- cryptography: Apache-2.0/BSD-3-Clause. 암호 프리미티브 구현과 OpenSSL 고지는 해당 배포 패키지 참조.
- Rust·wasm-pack·Docker·Node·Playwright·Chrome은 개발/검증 도구이며 실행 파일을 제품 패키지에 포함하지 않는다.
