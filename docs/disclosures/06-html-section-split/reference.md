# HTML Section Split Reference

## Paths

- `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/06-sections`에 `<YYYY>/<acpt_no>.html`을 저장한다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- KIND 본문과 목차 heading을 원본 구조로 보존한 입력 HTML 파일이다.

### `<data_root>/06-sections/<YYYY>/<acpt_no>.html`

#### I/O Structure

- 선택한 목차 heading과 그 범위의 본문을 보존한 출력 HTML 파일이다.
- HTML은 연도별 폴더에 저장하며 parser JSON은 만들지 않는다.
