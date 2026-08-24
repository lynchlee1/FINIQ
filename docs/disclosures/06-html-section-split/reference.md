# HTML Section Split Reference

## Paths

- `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/06-sections`에 `<YYYY>/<acpt_no>.html`을 저장한다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

#### I/O Structure

- KIND 본문과 생성 형식별 구조 경계를 원본 구조로 보존한 입력 HTML 파일이다.
- `workers`는 목차 조합 요약, 분리 저장과 결과 검사에서 동시에 처리할 HTML 파일 수를 정한다.

### `<data_root>/06-sections/<YYYY>/<acpt_no>.html`

#### I/O Structure

- 구조로 완전히 분리한 뒤 정정 section만 제외한 모든 목차 범위를 보존한 출력 HTML 파일이다.
- 정정 판별은 분리 후 section 제목의 공백을 제거하고 단일 토큰 `정정`만 확인한다. 목차 경계 탐지에는 문자열을 사용하지 않는다.
- Manual selection이나 모드별 저장 규칙은 사용하지 않는다.
- HTML은 연도별 폴더에 저장하며 parser JSON은 만들지 않는다.
