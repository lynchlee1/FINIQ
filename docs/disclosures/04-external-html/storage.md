# 04 파일과 저장 형식

- `<data_root>/03-filter/<mode>/filtered.json`을 입력으로 받아 `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`에 외부 HTML을, `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를, `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`에 압축한 문서 선택 정보를 저장한다.
- 압축 단계는 `data_root`와 `mode`에서 입력·출력 경로를 정하며, `<data_root>/04-external-html-compress/<mode>`가 없으면 저장할 때 생성한다.
- 파생 필터 `<parent_mode>/<mode>`는 `<data_root>/03-filter/<parent_mode>/subfilters/<mode>/filtered.json`의 멤버십을 사용하되 원본은 `<data_root>/04-external-html-download/<parent_mode>`, 압축 결과는 `<data_root>/04-external-html-compress/<parent_mode>`에서 읽는다. 두 폴더 모두 `subfilters/<mode>`나 자식 `mode`의 별도 출력 폴더는 만들지 않는다.

## `<data_root>/03-filter/<mode>/filtered.json`

- 입력 형식은 [03단계](../03-filter/storage.md)의 `filtered.json` 계약을 따른다.

## `<data_root>/04-external-html-download/<mode>/<YYYY>/<acpt_no>.html`

- 문서 선택 정보가 있는 KIND 외부 화면을 원본 구조로 보존한 출력 파일이다.

## `<data_root>/04-external-html-download/<mode>/kind_disclosure_html_manifest.json`

- [공통 HTML manifest 계약](../common/html-reuse.md#html-manifest)을 따른다.

## `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`

- 공시·문서 식별값, 선택한 본문 문서 번호와 필터 출처를 압축해 담은 출력 파일이다.
- `records[].selected_main_doc_no`에 선택한 본문 문서 번호를 기록한다.
- `records[].metadata`에는 입력 공시 metadata를 보존하며 `records[].metadata.disclosed_at`은 입력 항목의 `disclosed_at`과 같다.
- 각 record에도 외부 HTML의 `source_size_bytes`와 `source_sha256`을 기록한다.
- 파생 필터 작업은 상위 기본 필터 파일의 `records` 중 자식 `filtered.json`의 `acpt_no` 부분집합만 검증해 사용한다.
