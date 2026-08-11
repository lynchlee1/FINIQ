# HTML Section Split Features

## Purpose

KIND 본문에서 목차를 골라 해당 범위의 문서 구조를 보존한 HTML로 저장한다.

## Features

### Split HTML by Table of Contents

#### Behavior

- `disclosures/html_sections.py`는 `body` 바로 아래에서 `SECTION-N` class를 가진 heading(`h1`~`h6`)만 목차 경계로 사용한다.
- 원문 heading level과 `SECTION-N`, `id="toc_N"`의 숫자는 목차 번호로 사용하지 않고 본문 순서대로 내부 `toc_1`, `toc_2`, ...를 부여한다.
- 각 목차 heading부터 다음 목차 heading 직전까지를 같은 section으로 저장한다.
- HTML parser가 heading 안의 제목 `p`를 heading 바로 다음 형제 `p`로 옮기면 해당 `p`를 제목 요소로 사용한다.

#### Defaults and Exceptions

- 입력 파일을 읽거나 parsing하지 못하면 목록·요약·검사·저장 작업 전체를 실패 처리한다.
- 원문에 `head` 또는 `body`가 없거나 `body` 바로 아래에 대상 heading이 없으면 실패 처리한다.
- 선택한 heading과 parser가 바로 뒤로 옮긴 `p`에서 제목을 찾지 못하면 section 결과를 만들지 않는다.
- 목차와 제목은 선택한 heading과 바로 다음 `p`에서만 읽으며, 다른 요소나 새로 조합한 HTML은 사용하지 않는다.
- 목차 조합 요약, 분리 저장과 결과 검사는 설정한 worker 수 범위에서 HTML 파일별로 병렬 처리하고 입력 파일 순서로 결과를 합친다.

### Select Sections

#### Behavior

사용자가 체크박스, 전체 선택 또는 전체 해제로 저장할 목차를 직접 고른다.

#### Defaults and Exceptions

- 발견한 모든 목차는 선택하지 않은 상태로 표시한다.
- 전체 해제를 선택한 구성은 저장하지 않는다.
- 목차나 선택 결과가 없거나 선택하지 않은 구성이 하나라도 있으면 저장을 시작하지 않는다.

### Display Split Progress

#### Behavior

분리 결과를 바꾸지 않고 화면에 전달할 진행 내역만 제한한다.

- `기존 데이터 검토`는 첫 화면에 표시할 목록만이 아니라 입력 HTML 전체를 읽어 목차 구성과 문제 파일을 검사한다.
- 목차 HTML 저장 결과의 진행 내역은 생성 중부터 최근 200줄만 보관한다.

### Review an Unknown TOC Combination

#### Behavior

06단계가 저장 규칙이 없는 목차를 찾아 `needs_review`로 멈추면 다음 절차로 저장 범위를 정한다.

1. 공시 자동화 화면의 `목차 조합 모아보기`에서 처음 보는 목차 조합을 확인한다.
2. 저장할 목차를 체크박스로 고르고, 전체를 고르거나 빼려면 `전체 선택`과 `전체 해제`를 사용한다.
3. 모든 조합에서 저장할 목차를 골랐는지 확인한다. 저장할 목차가 없는 조합도 `전체 해제`로 판단을 남긴다.
4. `후속 실행`을 누르고 다음 단계가 시작되는지 확인한다.
