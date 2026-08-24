# HTML Section Split Features

## Purpose

KIND 본문을 생성 형식의 구조에 따라 모든 목차로 먼저 분리한 뒤, 정정 목차만 제거하고 나머지 범위의 문서 구조를 보존한 HTML로 자동 저장한다.

## TOC Boundary Safety Contract

- 목차 경계를 찾거나 전체 section을 분리하기 위해 표시 문자열을 하드코딩하는 방식을 금지한다. 정확히 같은 문자열, 부분 문자열, 정규식, 공백·기호 정규화, 문서 제목 목록 비교를 모두 포함한다. 이를 목차 분리 근거로 사용하는 것은 치명적인 파싱 실패로 본다.
- 표시 문자열은 DOM 구조로 모든 경계와 범위를 먼저 확정한 다음에만 사용할 수 있다. 현재 허용한 유일한 예외는 완전히 분리된 section 제목에서 공백을 제거하고 단일 토큰 `정정`의 포함 여부로 정정 section을 판별하는 후처리다. 이 토큰으로 경계를 발견하거나 범위를 늘리거나 줄여서는 안 된다.
- tag, DOM 계층, sibling 순서, class·id, anchor 연결은 원문 생성 형식의 구조 identifier로만 사용한다. class·id의 이름이 제목처럼 보인다는 이유로 의미를 추론하지 않고, 생성 형식과 전체 입력에서 위치·유일성을 검증한 식별자만 사용한다.
- 사업 모드별로 분기하지 않고 HTML 생성 형식의 구조로 분기한다. 검증된 구조가 아닌 입력은 문자열 규칙이나 다른 selector로 우회하지 않고 실패 처리한다.

### Verified Structural Expansion

2026-08-24에 05단계 저장 HTML 107,114건을 read-only로 전수 검사한 결과, 표시 문자열 비교 없이 다음 세 구조로 모두 분류되었다.

- `body` 직계 heading(`h1`~`h6`) + `SECTION-N`: 32,388건. 1개 문서는 경계 1개, 32,387개 문서는 경계 2개였다.
- `body` 직계 `p` + `SECTION-N`: 994건. 모든 문서의 경계가 2개였다.
- `body > div.xforms`의 주 콘텐츠 wrapper 직계 `div.xforms_title`: 73,732건. 모든 문서에서 이 위치의 경계가 정확히 1개였다. 하위 서식에 중첩된 `xforms_title` 2개는 주 wrapper 직계 조건에서 제외되었다.
- 미분류, 경계 없음, HTML parse 실패: 0건.

구조 확장은 문서마다 위 세 생성 형식 중 하나를 상호 배타적으로 확정한 뒤 해당 형식의 경계만 사용한다. heading `SECTION-N`이 있는 문서에서 HTML recovery parser가 heading 안의 제목 `p.SECTION-N`을 다음 sibling으로 옮길 수 있으므로, 이 `p`를 두 번째 경계로 중복 해석하지 않는다. heading 구조가 없고 `body` 직계 `p.SECTION-N`만 있을 때만 paragraph 형식으로 확정한다.

확정한 section container의 sibling 순서에서 내용이 있는 첫 경계 이전 preamble도 첫 section으로 분리하고, 각 경계부터 다음 경계 직전까지를 각각 section으로 삼는다. 따라서 정정 영역을 미리 버리지 않고 전체 목차 분리를 먼저 끝낸다. XForms는 경계가 `body` 직계가 아니므로 원문 document를 clone한 후 section container의 범위 밖 sibling만 제거해 조상 wrapper와 head를 보존한다. 세 생성 형식은 모두 구현하고 regression test로 고정했다.

같은 날 전수 결과를 DB 정정 여부와 대조한 결과, 일반공시 75,227건은 정정 section으로 판별된 항목이 0개였고 정정공시 31,887건은 모두 정확히 1개였다. 누락·중복·처리 오류는 0건이었다. 따라서 현재 저장 데이터에서는 공백 제거 후 단일 토큰 `정정` 하나만으로 충분하며, 다른 후보 문자열이나 모드별 규칙을 추가하지 않는다.

## Features

### Split HTML by Table of Contents

#### Behavior

- `disclosures/html_sections.py`는 문서마다 다음 세 생성 형식 중 하나를 확정한다: `body` 직계 heading + `SECTION-N`, heading이 없을 때의 `body` 직계 `p.SECTION-N`, XForms 주 콘텐츠 wrapper 직계 `div.xforms_title`.
- 원문 heading level과 `SECTION-N`, `id="toc_N"`의 숫자는 목차 번호로 사용하지 않고 본문 순서대로 내부 `toc_1`, `toc_2`, ...를 부여한다.
- 내용이 있는 첫 경계 이전 범위와 각 경계부터 다음 경계 직전까지를 빠짐없이 각각 section으로 분리한다.
- 전체 분리가 끝난 뒤 section 제목의 공백을 제거하고 단일 토큰 `정정`을 포함한 section만 제외한다.
- 정정 section을 제외한 모든 section을 하나의 유효한 HTML 문서로 자동 저장하며 Manual selection을 요구하지 않는다.
- HTML parser가 heading 안의 제목 `p`를 heading 바로 다음 형제 `p`로 옮기면 해당 `p`를 제목 요소로 사용한다.

#### Defaults and Exceptions

- 입력 파일을 읽거나 parsing하지 못하면 목록·요약·검사·저장 작업 전체를 실패 처리한다.
- 원문에 `head` 또는 `body`가 없거나 검증된 세 구조 중 하나로 유일하게 확정할 수 없으면 실패 처리한다. 다른 selector나 문자열 규칙으로 우회하지 않는다.
- 구조 경계와 parser가 바로 뒤로 옮긴 제목 `p`에서 제목을 찾지 못하면 실패 처리한다.
- 정정 section이 둘 이상이거나 정정 제거 뒤 업무 section이 하나도 남지 않으면 실패 처리한다.
- 이전 클라이언트가 `section_save_rules`를 보내도 저장 범위 결정에는 사용하지 않는다.
- 목차 조합 요약, 분리 저장과 결과 검사는 설정한 worker 수 범위에서 HTML 파일별로 병렬 처리하고 입력 파일 순서로 결과를 합친다.

### Display Split Progress

#### Behavior

분리 결과를 바꾸지 않고 화면에 전달할 진행 내역만 제한한다.

- `기존 데이터 검토`는 첫 화면에 표시할 목록만이 아니라 입력 HTML 전체를 읽어 목차 구성과 문제 파일을 검사한다.
- 저장 결과 검사는 입력 순서대로 만든 예상 HTML을 실제 파일과 즉시 비교하고, 이후 비교에는 상대 경로와 건수만 보관한다.
- 목차 HTML 저장 결과의 진행 내역은 생성 중부터 최근 200줄만 보관한다.
- 화면은 `기존 데이터 검토` 바로 아래에서 `조건검색 필터`를 선택하게 하고, 검사·개별 공시·저장은 모두 같은 기본 또는 파생 필터를 사용한다.
- 파생 필터는 상위 필터의 내부 HTML을 사용하되 `parent_mode`와 자식 `mode`를 함께 전달한다. 화면에 보이지 않는 이전 페이지의 모드를 대신 사용하지 않는다.

### Reject an Unknown TOC Structure

#### Behavior

06단계는 제목 조합을 사용자에게 물어보지 않는다. 검증된 세 생성 형식으로 구조를 확정할 수 없으면 해당 파일을 문제 파일로 보고 실패한다. 새 구조를 지원하려면 실제 원문 집합에서 위치와 유일성을 먼저 검증하고 구조 identifier와 regression test를 추가해야 한다. 정정 문자열 후보나 모드별 저장 규칙을 추가해 우회하지 않는다.
