# Security Transaction Parse Features

## Purpose

`security_transaction` mode로 발행증권거래 공시를 읽는다.

## Features

### Select the Security Transaction Mode

#### Behavior

- `parse_security_transaction()`이 `security_transaction` mode에 공통 원본 표 변환을 적용한다.
- 공통 식별값과 원본 `raw_tables`를 만들고 mode 전용 schema는 빈 객체로 둔다.

#### Defaults and Exceptions

- mode 전용 업무값, `field_parse_status`와 parser warning은 만들지 않는다.
- `raw_tables`는 preview와 parser 내부에서만 사용하고 최종 JSON의 record에서는 제거한다.
