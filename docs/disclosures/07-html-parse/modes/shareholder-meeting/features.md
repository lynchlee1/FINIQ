# Shareholder Meeting Parse Features

## Purpose

`shareholder_meeting` mode로 주주총회 안건, 선임 내역과 사업목적 변경을 추출한다.

## Features

### Select the Shareholder Meeting Mode

#### Behavior

- `parse_shareholder_meeting()`이 `shareholder_meeting` mode의 업무값을 공통 record에 추가한다.

### Parse Agendas

#### Behavior

- 안건 원문은 확정한 이름의 바로 다음 `td`를 줄 단위로 읽고 빈 줄과 `-`를 제거한다.
- `제1호`, `안건`, `-제1`, `가.`, `나.`, `[`, `<`로 시작하는 줄은 새 안건으로 만들고 나머지는 앞 안건에 이어 붙인다.
- 결과는 `agendas`와 `agenda_items`에 저장한다.

#### Defaults and Exceptions

- 07단계 parser는 외부 title이나 `RESULT`·`NOTICE` 구분을 받지 않는다. `1. 결의사항`, `3. 의안 주요내용` 또는 `결의사항`과 일치하는 첫 `td`를 문서 순서대로 사용한다.
- 유효한 목차나 행이 없으면 빈 목록을 저장한다.

### Parse Election Details

#### Behavior

- `이사선임 세부내역`, `사외이사선임 세부내역`, `감사선임 세부내역`을 각각 `director_elections`, `outside_director_elections`, `auditor_elections`에 저장한다.
- 세 목록은 위 순서로 `elections`에도 합치고 성명이 비거나 `-`인 줄은 제외한다.
- 각 항목에는 원래 표 값과 `section_title`, `section_type`, `name`, `birth_month`, `term`, `is_new`, `is_full_time`, `major_career`, `other_company`를 넣는다.

#### Defaults and Exceptions

- 모든 `span` 중 정확히 같은 첫 목차 제목 뒤의 첫 표를 사용한다.
- 중복 제목에는 `_1`, `_2`, 빈 제목에는 `unknown`을 붙이며 유효한 목차나 행이 없으면 빈 목록을 저장한다.

### Parse Business Purpose Changes

#### Behavior

- 사업목적 항목에는 `category`와 `reason`을 넣고 `구분`이 비었거나 `내용`이 `변경전` 또는 `내용`인 제목 줄은 제외한다.
- `구분=사업목적 변경`이면 `내용`과 `내용_1`을 `before`·`after`, 나머지는 `content`로 저장한다.
- `business_purpose_changes` key는 항상 만든다.

#### Defaults and Exceptions

- 유효한 목차나 행이 없으면 빈 목록을 저장한다.
