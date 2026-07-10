# Completed Changes

## 2026-07-10 — HTML 파서 공통 문서 책임 분리

- 목적: 한 문서에 섞여 있던 공통 parsing 동작, 데이터 구조, 예외 처리 계약을 책임별로 분리한다.
- 구현: `docs/common/` 아래에서 기존 공통 로직 문서에는 parsing과 metadata 연결 흐름만 남기고, table/base record/저장 payload 구조와 상태/경고/실행 오류 처리를 각각 독립 문서로 이동했다. 개별 parser 문서와 문서 라우팅의 참조도 새 경계와 경로에 맞췄다.
- 검증: 상대 Markdown link와 `git diff --check`를 확인했다.

## 2026-07-10 — HTML 파서 정정신고 table 중복 필터 제거

- 목적: section pre-cleaning에서 이미 제거되는 정정신고 table을 사채·유무상증자 parser가 다시 판별하고 제외하던 중복 기능을 없앤다.
- 구현: 공통 정정 chapter 판별 및 table/row 필터 helper와 export를 삭제하고, 사채·유무상증자 parser가 pre-cleaning된 입력 table을 직접 선택하도록 단순화했다. 공통 및 parser별 규칙 문서에서도 parser 내부 정정신고 table 필터 규칙을 제거했다.
- 실제 리소스 검증: `resources/KIND/bond_issuance/kind_html_contents_grouped_sections` 15,175건과 `resources/KIND/rights_issuance/kind_html_contents_sections` 19,975건을 확인한 결과, 기존 정정 chapter 판별에 해당하는 파일과 table은 모두 0건이었다.
- 회귀 검증: 관련 모듈 `py_compile` 통과, `tests/market_desk/test_kind_web_service.py` 402개 통과.

## 2026-07-10 — 공시원문 변환 fallback 축소와 열 위치 보존

- 목적: 번호 라벨 정규화를 단순 선행 `숫자.` 형식으로 제한하고, 열 기반 표에서 압축 행 때문에 대상자명·수량 열이 어긋나는 문제를 제거하며, 실제 데이터에서 쓰이지 않는 빈 슬롯 보충과 `option_index=0` fallback을 삭제한다.
- 구현: 라벨 정규화 후 정확히 일치하는 행만 인정하고, 테이블에 열 위치 보존용 `positional_rows`를 추가했다. 사채 투자자 표와 유무상증자 제3자배정 표는 compact `logical_rows`로 표를 찾은 뒤 서로 다른 선언 대상자명·수량 열을 `positional_rows`에서만 읽도록 분리했다. 두 헤더 문구가 한 셀에 섞인 가짜 후보는 거부한다. 합성 빈 슬롯 삽입과 잘못된 `option_index`의 0 대체를 제거하고 관련 규칙 문서를 맞췄다.
- 실제 리소스 검증: `resources/KIND/bond_issuance` HTML 15,175건의 납입일 라벨은 모두 `11.`/`12.`/`13.` 접두사였고 정규화 후 전부 추출됐다. `resources/KIND/rights_issuance` HTML 19,975건의 제3자배정 대상 표 후보 13,092개 중 정상 13,091개는 선언 열 인덱스 누락과 짧은 행이 0건이었고, 한 셀에 두 문구가 섞인 정정 설명표 1개는 거부했다. compact/positional 위치가 달라지는 유무상증자 데이터행 2,205개와 사채 데이터행 2,899개를 positional 기준으로 처리했다. 양쪽 304,678개 표에서 합성 빈 슬롯 분기는 0회였고, 두 `compressed-external-html.json`의 정정 묶음 후보 `option_index`는 모두 정수였다.
- 회귀 검증: 관련 모듈 `py_compile` 통과, `tests/market_desk/test_kind_web_service.py` 403개 통과.

## 2026-07-10 — HTML 파서 기술 규칙 문서 정리

- 목적: 공통 HTML 구조화, 사채 추출, 유무상증자 추출의 실제 label·table·상태·경고·기존 fallback 규칙을 기능별로 이해하기 쉽게 기록한다.
- 구현: 공통 문서에는 decoding, span 확장, `logical_rows`/`positional_rows`, base record, metadata 연결·저장 규칙을 정리했다. 사채와 유무상증자 문서에는 유형 판정, table 선택, 필드 추출, 상세 객체, 상태, 검증, fallback과 fallback 금지 조건을 실제 구현에 맞춰 기록했다.
- 검증: 고정된 `README.md`와 `external-metadata.md`의 작업 전·후 SHA-256이 동일함을 확인했다. 상대 Markdown link 6개와 `git diff --check`가 통과했고, `resources/`를 대상으로 하지 않는 공통 table·채권·유무상증자·metadata workflow 합성 test 38개가 통과했다.
