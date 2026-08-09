# Shareholder Meeting Parse Reference

## Paths

- `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/shareholder_meeting/parsed-shareholder_meeting.json`에 구조화 결과를 저장한다.

### `<data_root>/07-converted/shareholder_meeting/parsed-shareholder_meeting.json`

#### I/O Structure

- 안건, 선임 내역과 사업목적 변경 record를 담은 출력 파일이다.
- `agendas`와 `agenda_items`는 같은 안건 문자열 배열이다.
- `elections`는 `director_elections`, `outside_director_elections`, `auditor_elections`를 이 순서로 합친 배열이다.
- `business_purpose_changes`는 `category`, `reason`과 `before`·`after` 또는 `content`를 가진 객체 배열이다.

#### Defaults and Exceptions

- 외부 title을 연결하지 않으므로 공통 `title`은 빈 문자열이다. `field_parse_status`와 parser warning은 포함하지 않는다.
