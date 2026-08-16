# Internal HTML Download Reference

## Paths

- `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`을 입력으로 받아 `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`에 본문 HTML을, `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를 저장한다.

### `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`

#### I/O Structure

- 접수번호, 공시일 metadata와 선택한 본문 문서 번호를 담은 입력 파일이다.
- `records[].acpt_no`는 저장할 공시를 식별한다.
- `records[].selected_main_doc_no`는 선택한 본문 문서 번호다.
- `records[].metadata.disclosed_at`은 ISO 날짜로 시작한다.
- `max_workers`는 동시에 처리할 공시 대상 수를 정한다. 실제 KIND 요청 시작 간격은 worker와 연도 그룹 사이에서도 공유한다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- KIND에서 받은 공시 본문 HTML을 원본 구조로 보존한 출력 파일이다.
- `<YYYY>`는 입력 record의 `metadata.disclosed_at` 연도다.

### `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`

#### I/O Structure

- 본문 HTML을 원본 공시 metadata와 연결하는 출력 파일이다.
- 파일마다 `source_size_bytes`와 `source_sha256`을 기록한다.
- `format`은 `finiq_disclosure_html_manifest_v2`이며 입력 JSON 전체를 대상으로 한 `source_fingerprint`는 기록하지 않는다. 재사용 판정은 접수번호별 `source_sha256`만으로 하므로 필터를 다시 실행해도 기존 HTML이 무효화되지 않는다.
- 구버전 `finiq_disclosure_html_manifest_v1`은 읽기만 지원하며, 이 경우에만 `source_fingerprint` 비교를 유지한다.
