# Mixed Rights Issuance Features

## Purpose

유무상증자 공시의 유상 부분과 무상 부분을 나누어 두 상세 결과를 만든다.

## Features

### Split Paid and Bonus Sections

#### Behavior

- 합친 줄에서 앞 번호와 공백을 제거한 `N=1`이 `무상증자`와 정확히 일치하는 첫 한 칸짜리 행을 구분점으로 사용한다.
- 앞 번호가 없는 `무상증자`도 같은 구분점으로 사용한다.
- 구분점 앞은 유상 부분, 뒤는 무상 부분으로 처리한다.

#### Defaults and Exceptions

- 외부 제목이 유무상증자인데 구분점을 찾지 못하면 실패 처리한다.

### Build Paid-Issuance Details

#### Behavior

- 공통 유상 상세 규칙을 구분점 앞의 유상 부분에 적용한다.

#### Defaults and Exceptions

- 유상 부분의 값이 누락돼도 선택하지 않은 표나 최상위 값으로 채우지 않는다.

### Build Bonus-Issuance Details

#### Behavior

- 수량, 증자 전 수량, 배정기준일, 1주당 배정수, 교부예정일과 상장예정일을 무상 부분에서 다시 읽어 `무상증자`에 저장한다.

#### Defaults and Exceptions

- 무상 부분의 값이 누락돼도 최상위 값이나 유상 상세값으로 채우지 않는다.
