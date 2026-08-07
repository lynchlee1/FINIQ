# 외부 HTML 저장 Reference

## 경로

- `<data_root>/03-filter/<mode>/filtered.json`을 입력으로 받아 `<data_root>/04-external-html-download/<mode>`에 `<YYYY>/<acpt_no>.html`, `kind_disclosure_html_manifest.json`, `compressed-external-html.json`을 저장한다.

## 입력 형식

### `filtered.json`

- 검색 조건으로 고른 공시와 접수번호, 공시일 metadata를 담은 파일이다.

## 출력 형식

### `<YYYY>/<acpt_no>.html`

- 문서 선택 정보가 있는 KIND 외부 화면을 원본 구조로 보존한 파일이다.

### `kind_disclosure_html_manifest.json`

- 외부 HTML을 원본 공시 metadata와 연결하고 파일 크기와 SHA-256을 기록한 파일이다.

### `compressed-external-html.json`

- 공시·문서 식별값과 선택한 본문 문서 번호를 압축해 담은 파일이다.
