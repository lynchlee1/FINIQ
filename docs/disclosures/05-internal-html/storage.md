# 05 파일과 저장 형식

- `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`을 입력으로 받아 `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`에 본문 HTML을, `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를 저장한다.
- 파생 필터 `<parent_mode>/<mode>`는 상위 `<data_root>/04-external-html-compress/<parent_mode>/compressed-external-html.json`과 `<data_root>/05-internal-html-download/<parent_mode>` 산출물을 사용한다. 자식 `mode`나 `subfilters/<mode>`의 05단계 출력 폴더는 만들지 않는다.

## `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`

- 입력 형식은 [04단계](../04-external-html/storage.md)의 `compressed-external-html.json` 계약을 따른다.

## `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

- KIND에서 받은 공시 본문 HTML을 원본 구조로 보존한 출력 파일이다.
- `<YYYY>`는 입력 record의 `metadata.disclosed_at` 연도다.

## `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`

- [공통 HTML manifest 계약](../common/execution.md#html-manifest)을 따른다.
- 파생 필터 작업은 상위 manifest와 HTML 중 자식 `filtered.json`의 `acpt_no` 부분집합만 검증해 사용하며 `selected_main_doc_no`도 상위 04단계 record와 일치해야 한다.
