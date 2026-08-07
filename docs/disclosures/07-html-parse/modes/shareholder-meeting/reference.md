# Shareholder Meeting Parse Reference

## Paths

- `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/shareholder_meeting/parsed-shareholder_meeting.json`에 구조화 결과를 저장한다.

### `<data_root>/07-converted/shareholder_meeting/parsed-shareholder_meeting.json`

#### I/O Structure

- 안건, 선임 내역과 사업목적 변경 record를 담은 출력 파일이다.

#### Defaults and Exceptions

- 외부 `title`, `field_parse_status`와 warning은 포함하지 않는다.
