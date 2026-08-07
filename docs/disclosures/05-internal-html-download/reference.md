# 본문 HTML 저장 Reference

## 경로

- `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`을 입력으로 받아 `<data_root>/05-internal-html-download/<mode>`에 `<YYYY>/<acpt_no>.html`과 `kind_disclosure_html_manifest.json`을 저장한다.

## 입력 형식

### `compressed-external-html.json`

- 접수번호, 공시일 metadata, 선택한 본문 문서 번호를 담은 다운로드 대상 파일이다.
- `compressed-external-html.json`만 입력으로 사용한다.

## 출력 형식

### `<YYYY>/<acpt_no>.html`

- KIND에서 받은 공시 본문 HTML을 원본 구조로 보존한 파일이다.
- 결과 HTML은 각 record의 `metadata.disclosed_at` 연도에 따라 연도별 하위 디렉터리에 저장한다.

### `kind_disclosure_html_manifest.json`

- 본문 HTML을 원본 공시 metadata와 연결하고 파일 크기와 SHA-256을 기록한 파일이다.
