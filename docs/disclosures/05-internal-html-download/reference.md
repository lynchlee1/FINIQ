# Internal HTML Download Reference

## Paths

- `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`을 입력으로 받아 `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`에 본문 HTML을, `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를 저장한다.

### `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`

#### I/O Structure

- 접수번호, 공시일 metadata와 선택한 본문 문서 번호를 담은 입력 파일이다.
- `records[].acpt_no`는 저장할 공시를 식별한다.
- `records[].selected_main_doc_no`는 선택한 본문 문서 번호다.
- `records[].metadata.disclosed_at`은 ISO 날짜로 시작한다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- KIND에서 받은 공시 본문 HTML을 원본 구조로 보존한 출력 파일이다.
- `<YYYY>`는 입력 record의 `metadata.disclosed_at` 연도다.

### `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`

#### I/O Structure

- 본문 HTML을 원본 공시 metadata와 연결하는 출력 파일이다.
- 파일마다 `source_size_bytes`와 `source_sha256`을 기록한다.
- 입력 JSON의 절대 경로 대신 내용으로 계산한 `source_fingerprint`를 기록한다.
