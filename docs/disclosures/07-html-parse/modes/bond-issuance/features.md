# Bond Issuance Parse Features

## Purpose

`bond_issuance` mode로 CB·EB·BW 공시의 사채 조건, 자금조달 목적과 투자자를 추출한다.

## Features

### Select the Bond Issuance Mode

#### Behavior

- `parse_bond_issuance()`가 `bond_issuance` mode의 업무값을 공통 record에 추가한다.

### Connect Company Metadata

#### Behavior

- metadata에 회사명이 있으면 `corp_name`에 저장한다.

### Find Fixed Cell Positions

#### Behavior

- 라벨은 해당 칸 앞 번호와 공백을 제거한 뒤 검사한다.
- 메인 표 field는 연속 중복을 압축한 `logical_rows`를 기준으로 왼쪽부터 셀 위치 `N`을 고정한다.
- 정해진 위치의 라벨이 일치하는 첫 행을 찾고 값은 맨 오른쪽 셀에서 읽는다.

#### Defaults and Exceptions

- 첫 일치 행의 값이 비거나 변환할 수 없어도 다른 이름이나 뒤 행으로 바꾸지 않는다.
- 한 행에 여러 업무값이 있거나 값 열이 양식마다 다른 field는 해당 기능의 별도 위치 규칙을 따른다.

### Select the Bond Terms Table

#### Behavior

- `사채의 종류`, `사채의 권면`, `자금조달의 목적`을 모두 가진 첫 표를 `logical_rows`로 확인해 사용한다.

#### Defaults and Exceptions

- 해당 표가 없으면 일부 값만 만들지 않고 즉시 실패 처리한다.

### Select the Investor Table

#### Behavior

- 첫 줄의 서로 다른 열에 `발행 대상자명`과 `발행권면`이 있는 첫 표를 사용한다.
- `positional_rows`의 column header에서 두 열을 확정하고 모든 데이터 줄에서 같은 열을 읽는다.

#### Defaults and Exceptions

- 해당 표가 없으면 `투자자`를 `null`, 상태를 `source_not_found`로 기록하고 strong warning을 만든다.
- 투자자 표에는 메인 표의 고정 N 규칙을 적용하지 않는다.

### Determine the Bond Type

#### Behavior

- 외부 `title`에서 CB → EB → BW 순서로 확인하며 정확히 하나만 맞으면 `종류`에 저장한다.
- 행사대상·행사가액·행사기간도 CB·EB·BW마다 대칭인 이름 순서를 유지한다.

#### Defaults and Exceptions

- `종류`는 표에서 읽지 않으므로 공통 값 위치 규칙을 적용하지 않는다.

### Parse the Bond Round

#### Behavior

- `N=2`가 정확히 `회차`인 첫 줄의 `N=3` 값을 사용한다.

#### Defaults and Exceptions

- 값이 맨 오른쪽에 있지 않으므로 공통 값 위치 규칙을 적용하지 않는다.

### Parse the Issue Amount

#### Behavior

- 일반 양식은 `N=1`이 `사채의 권면`으로 시작하는 첫 줄의 맨 오른쪽 값을 사용한다.
- 외화·원화가 나뉜 해외사채 양식은 `N=2`가 `원화기준 (원)`인 줄의 맨 오른쪽 값을 사용한다.

#### Defaults and Exceptions

- 선택한 줄에서 숫자를 읽지 못해도 다른 줄로 바꾸지 않는다.

### Parse the Maturity Date

#### Behavior

- `N=1`이 정확히 `사채만기일` → `사채만기`인 순서로 찾은 첫 줄의 맨 오른쪽 값을 사용한다.

### Parse the Exercise Target

#### Behavior

- `전환대상`, `교환대상`, `인수권행사대상`, `전환에 따라`, `교환에 따라`, `인수권행사에 따라`, `전환으로 발행할`, `교환으로 발행할`, `인수권행사로 발행할`, `신주인수권행사에 따라` 순서로 확인한다.
- `N=2`가 해당 이름으로 시작하는 첫 줄의 맨 오른쪽 값을 사용한다.

#### Defaults and Exceptions

- 먼저 찾은 이름의 값이 비어 있어도 다음 이름 행으로 바꾸지 않는다.

### Parse the Exercise Price

#### Behavior

- 공백을 제거한 `N=2`를 `전환가액 (원/주)`, `교환가액 (원/주)`, `행사가액 (원/주)`, `전환가격 (원/주)`, `교환가격 (원/주)`, `행사가격 (원/주)` 순서로 정확히 일치시킨다.
- 첫 일치 행의 맨 오른쪽 셀 하나만 숫자로 변환한다.

#### Defaults and Exceptions

- 변환할 수 없어도 다음 이름이나 행을 사용하지 않는다.

### Parse the Payment Date

#### Behavior

- `N=1`이 정확히 `납입일`인 첫 줄의 맨 오른쪽 값을 사용한다.

### Parse the Exercise Period

#### Behavior

- `N=2`가 `전환청구기간`, `교환청구기간`, `권리행사기간`, `행사기간`인 순서로 찾는다.
- `N=3`이 `시작일`인 줄의 맨 오른쪽 값을 시작일, `종료일`인 줄의 맨 오른쪽 값을 종료일로 사용한다.

#### Defaults and Exceptions

- 시작일과 종료일은 따로 읽으며 서로 바꾸거나 뒤의 다른 기간 이름으로 보완하지 않는다.

### Parse the Issuance Method

#### Behavior

- `N=1`이 정확히 `사채발행방법`인 첫 줄의 맨 오른쪽 값을 사용한다.

### Parse Funding Purposes

#### Behavior

- `N=1`이 정확히 `자금조달의 목적`인 모든 줄을 사용한다.
- 목적명은 `N=2`, 금액은 맨 오른쪽 값에서 읽은 숫자를 사용한다.

#### Defaults and Exceptions

- 0이나 `-`인 항목과 목적명만 있고 금액이 없는 줄은 제외한다.
- 모든 줄에서 금액을 찾지 못하면 `발행목적` 전체를 `source_not_found`로 처리한다.

### Parse Investors

#### Behavior

- 선택한 투자자 표에서 이름과 발행권면총액을 원본 순서대로 저장한다.

#### Defaults and Exceptions

- 이름이 빈 값·`-`·합계 표현이면 제외하고 금액 `-`는 0으로 남긴다.
- 첫 유효 표에 남길 줄이 없으면 `null`로 끝내며 다른 표나 열로 보완하지 않는다.

### Record Bond Field Status

#### Behavior

- 모든 업무값에 상태를 기록한다.
- `발행금액`이 0이나 `-`이면 `explicit_zero`로 기록한다.
- 발행목적에 양수 항목이 있으면 `parsed`, 숫자는 있지만 남길 항목이 없으면 `explicit_zero`, 숫자가 없으면 `source_not_found`다.

#### Defaults and Exceptions

- 이 parser는 medium warning을 직접 만들지 않는다.

### Validate Bond Totals

#### Behavior

- 발행목적 합계나 투자자 합계가 발행금액과 다르면 허용 오차 없이 weak warning을 만든다.

#### Defaults and Exceptions

- 합계가 달라도 원본에서 읽은 값은 고치지 않는다.

### Inspect Bond Parse Results

#### Behavior

- 조회 함수는 저장한 결과에서 사채 요약을 만든다.

### Investigate Bond Parser Problems

#### Behavior

- 06단계 HTML과 `resources/KIND/bond_issuance`의 실제 KIND 파일을 대조한다.
