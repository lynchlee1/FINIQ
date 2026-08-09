# External HTML Download Reference

## Paths

- `<data_root>/03-filter/<mode>/filtered.json`을 입력으로 받아 `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`에 외부 HTML을, `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를, `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`에 압축한 문서 선택 정보를 저장한다.

### `<data_root>/03-filter/<mode>/filtered.json`

#### I/O Structure

- 검색 조건으로 고른 공시의 접수번호와 공시일 metadata를 담은 입력 파일이다.
- `format`은 `kind_disclosure_filter_v1`이고 객체 맨 위의 `disclosures` 목록만 입력으로 사용한다.
- 각 항목은 비어 있지 않은 `acpt_no`와 ISO 날짜로 시작하는 `disclosed_at`을 가진다.

### `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- 문서 선택 정보가 있는 KIND 외부 화면을 원본 구조로 보존한 출력 파일이다.
- `<YYYY>`는 입력 항목의 `disclosed_at` 연도다.

### `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`

#### I/O Structure

- 외부 HTML을 원본 공시 metadata와 연결하는 출력 파일이다.
- 파일마다 `source_size_bytes`와 `source_sha256`을 기록한다.
- 입력 JSON의 절대 경로 대신 내용으로 계산한 `source_fingerprint`를 기록한다.

### `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`

#### I/O Structure

- 공시·문서 식별값, 선택한 본문 문서 번호와 필터 출처를 압축해 담은 출력 파일이다.
- `records[].selected_main_doc_no`에 선택한 본문 문서 번호를 기록한다.
- `records[].metadata`에는 입력 공시 metadata를 보존하며 `records[].metadata.disclosed_at`은 입력 항목의 `disclosed_at`과 같다.
- 각 record와 manifest에 외부 HTML의 `source_size_bytes`와 `source_sha256`을 기록한다.
