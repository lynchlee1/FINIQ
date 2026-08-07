# 공시원문 변환 Reference

## 경로

- `<data_root>/03-filter/<mode>/filtered.json`, `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`, `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/<mode>`에 `parsed-<mode>.json`을 저장한다.

## 입력 형식

### `filtered.json`

- 선택한 공시의 제목, 회사, 시장, 공시일 metadata를 담은 파일이다.

### `compressed-external-html.json`

- 공시·문서 식별값과 선택한 본문 문서 번호를 담은 파일이다.

### `<YYYY>/<acpt_no>.html`

- 선택한 목차 범위의 공시 본문을 보존한 parser 입력 HTML이다.

## 출력 형식

### `parsed-<mode>.json`

- mode별 구조화 record, correction family, warning, error와 실행 집계를 담은 파일이다.
- `/html-parse`에서 변환 유형을 선택해 parsing하거나 preview할 때 적용한다.
- 원본 HTML은 수정하지 않는다.
