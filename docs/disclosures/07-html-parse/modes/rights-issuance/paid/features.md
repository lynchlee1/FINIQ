# Paid Rights Issuance Features

## Purpose

외부 제목에서 `유상증자`를 확인한 공시의 자금 사용처, 발행가액, 방식, 일정과 발행대상자를 추출한다.

## Features

### Parse Funding Purposes

#### Behavior

- `N=1`이 `자금조달의 목적`과 정확히 일치하는 모든 행에서 `N=2`의 사용처명과 맨 오른쪽 금액을 HTML 순서대로 읽는다.

#### Defaults and Exceptions

- 0이나 `-`인 항목은 제외한다.
- 숫자를 하나도 읽지 못하면 `null`과 `source_not_found`, 숫자는 있지만 양수 항목이 없으면 빈 목록과 `explicit_zero`를 기록한다.
- 사용처명에서는 원 단위 표기만 제거하며 허용 이름이나 탐색 순서를 하드코딩하지 않는다.

### Parse Issue Prices

#### Behavior

- 일반 양식은 `N=1`이 `신주 발행가액`, `N=2`가 주식 종류인 첫 행의 맨 오른쪽 값을 읽는다.
- 예정·확정 양식은 `N=1`이 `신주 발행가액`, `N=2`가 `확정발행가`, `N=3`이 주식 종류인 첫 행의 맨 오른쪽 값을 읽는다.

#### Defaults and Exceptions

- 보통주식·기타주식 두 항목을 항상 유지한다.
- 첫 일치 행의 0이나 `-`를 뒤 행의 양수로 바꾸지 않으며 숫자를 읽지 못한 종류는 `null`이다.
- `N=2`가 `예정발행가`인 행은 맨 오른쪽이 확정예정일이므로 사용하지 않는다.

### Parse Method and Payment Date

#### Behavior

- `N=1`이 `증자방식` 또는 `납입일`과 정확히 일치하는 첫 행의 맨 오른쪽 값을 각 field에 저장한다.

### Build Paid-Issuance Details

#### Behavior

- 최상위 수량·목적·가액·방식·납입일·일정·발행대상자를 `유상증자`에 저장한다.
- `신주배정기준일`과 `1주당 신주배정주식수`는 유상 부분에서 따로 읽는다.
- `무상증자`는 `null`로 저장한다.
