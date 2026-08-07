# Disclosure HTML Parse Reference

## Paths

- `<data_root>/03-filter/<mode>/filtered.json`, `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`, `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/<mode>`에 `parsed-<mode>.json`을 저장한다.

### `<data_root>/03-filter/<mode>/filtered.json`

#### I/O Structure

- 선택한 공시의 제목, 회사, 시장과 공시일 metadata를 담은 입력 파일이다.

### `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`

#### I/O Structure

- 공시·문서 식별값과 선택한 본문 문서 번호를 담은 입력 파일이다.

### `<data_root>/06-sections/<YYYY>/<acpt_no>.html`

#### I/O Structure

- 선택한 목차 범위의 공시 본문을 보존한 입력 HTML 파일이다.

### `<data_root>/07-converted/<mode>/parsed-<mode>.json`

#### I/O Structure

- mode별 구조화 record, correction family, warning, error와 실행 집계를 담은 출력 파일이다.
- 원본 HTML은 수정하지 않는다.
