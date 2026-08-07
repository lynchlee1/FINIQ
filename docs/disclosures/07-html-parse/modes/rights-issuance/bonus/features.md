# Bonus Rights Issuance Features

## Purpose

외부 제목에서 `무상증자`를 확인한 공시의 무상 배정 수량과 일정을 저장하고 적용하지 않는 유상 항목을 구분한다.

## Features

### Mark Paid-Issuance Fields as Not Applicable

#### Behavior

- `발행목적`, `발행가액`, `증자방식`, `납입일`, `발행대상자`는 검색하지 않는다.
- 각 값에는 `-`, 상태에는 `not_applicable`을 기록하며 warning과 합계 검증에서 제외한다.

### Build Bonus-Issuance Details

#### Behavior

- `신주의 종류와 수`, `증자 전 발행주식총수`와 공통 일정값을 무상증자 부분에서 읽어 최상위와 `무상증자`에 저장한다.
- `유상증자`는 `null`로 저장한다.

#### Defaults and Exceptions

- 무상 상세값이 누락돼도 최상위 값으로 채우지 않는다.
