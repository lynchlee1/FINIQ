# External HTML Download Reference

## Paths

- `<data_root>/03-filter/<mode>/filtered.json`을 입력으로 받아 `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`에 외부 HTML을, `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를, `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`에 압축한 문서 선택 정보를 저장한다.

### `<data_root>/03-filter/<mode>/filtered.json`

#### I/O Structure

- 검색 조건으로 고른 공시의 접수번호와 공시일 metadata를 담은 입력 파일이다.
- `format`은 `kind_disclosure_filter_v1`이고 객체 맨 위의 `disclosures` 목록만 입력으로 사용한다.
- 각 항목의 `acpt_no`는 로마자를 포함할 수 있는 텍스트이고 `disclosed_at`은 ISO 날짜로 시작한다.

### `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- 문서 선택 정보가 있는 KIND 외부 화면을 원본 구조로 보존한 출력 파일이다.
- 파일명의 `acpt_no`는 로마자를 포함할 수 있는 텍스트다.

### `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`

#### I/O Structure

- 외부 HTML을 원본 공시 metadata와 연결하는 출력 파일이다.
- 파일마다 `source_size_bytes`와 `source_sha256`을 기록한다.

### `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`

#### I/O Structure

- 공시·문서 식별값, 선택한 본문 문서 번호와 필터 출처를 압축해 담은 출력 파일이다.
- `records[].acpt_no`는 로마자를 포함할 수 있는 텍스트다.
- `records[].selected_main_doc_no`에 선택한 본문 문서 번호를 기록한다.
- 각 record와 manifest에 외부 HTML의 `source_size_bytes`와 `source_sha256`을 기록한다.
