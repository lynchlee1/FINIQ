# HTML Change Log Features

## Purpose

07단계에서 만든 정정공시 family를 읽어 문서 순서에 따른 mode별 값 변화를 비교하고 `/html-change-log`에서 결과를 조회한다.

## Features

### Select Correction Families

#### Behavior

- family ID가 있고 문서 순서가 정수이며 문서가 2개 이상인 결과만 선택한다.
- family ID가 큰 순서로 정렬한다.

#### Defaults and Exceptions

- 변환 결과 파일이 없거나 읽을 수 없으면 실패 처리한다.

### Compare Adjacent Documents

#### Behavior

- family 안의 문서를 공시 순서와 접수번호로 정렬한다.
- 최초 공시부터 최신 정정공시까지 이웃한 두 문서의 비교 항목을 그대로 비교한다.
- 변경 전후 값과 변경 항목을 비교 결과에 유지한다.

### Apply Change Thresholds

#### Behavior

- 날짜 차이가 설정한 일수 이하이거나 수치 차이가 설정한 비율 이하이면 작은 변동으로 본다.
- 목록은 구조와 순서가 같고 모든 수치 차이가 기준 이하일 때만 작은 변동으로 본다.
- `회차`의 변경은 주요 변동으로 집계하지 않는다.

#### Defaults and Exceptions

- 날짜는 한글 날짜, 점이나 하이픈 한 가지로 나눈 날짜 또는 `YYYYMMDD` 형식만 읽고 실제로 없는 날짜는 읽지 않는다.
- 수치는 부호, 숫자, 올바른 쉼표와 소수점만 있을 때 읽는다. 목록과 묶음 안의 수치도 같은 기준으로 읽고 순서는 바꾸지 않는다.
- 날짜나 수치를 읽지 못하면 작은 변동에서 제외하지 않는다.

### Filter and Export Results

#### Behavior

- 제목, 접수번호와 항목 이름으로 검색한다.
- `변경사항만 보기`는 주요 변경이 있는 family만 결과에 포함한다.
- `최신버전만`을 선택하면 family마다 최신 문서만 Excel에 넣는다.

### Request Change Logs

#### Behavior

화면에서 결과 폴더, 변환 유형, 조회 개수와 변동 임계값을 비교 요청으로 전달한다.

#### Defaults and Exceptions

- 변동 임계값을 지정하지 않으면 날짜는 3일, 수치는 1%를 사용한다.
- 결과 폴더나 변환 유형이 없거나, 지원하지 않는 변환 유형·잘못된 폴더·1보다 작은 조회 개수를 지정하면 실패 처리한다.

### Display Correction Families

#### Behavior

- 비교 결과에 포함한 family 가운데 화면에서 정한 개수만 보여 준다.
- 처음에는 문서 수, 제목과 바뀐 항목만 보여 주고 family를 선택하면 상세 내용을 불러온다.
- 바뀐 항목 이름 일부와 나머지 개수를 보여 준다.

### Display Change Details

#### Behavior

- 문서 정보와 변경 전후 값을 함께 보여 주며 바뀐 항목은 행, 공시 순서는 열로 표시한다.
- 목록은 쉼표로 잇고 빈 값은 `-`로 표시한다.
- 발행금액과 발행가액은 숫자일 때 억 원 단위로 보여 준다.
- 요청한 항목과 관계없는 내용은 제외한다.

#### Defaults and Exceptions

- 변경 기록이 없거나 문서 위치를 찾지 못한 칸은 비워 둔다.
- 발행금액이나 발행가액이 숫자가 아니면 원래 값을 보여 준다.
- 발행대상자나 투자자 금액을 읽지 못하면 각 항목을 공백으로 이어 표시한다.
