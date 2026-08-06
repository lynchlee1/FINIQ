# 주주총회 변환

## 목적

- `shareholder_meeting` mode가 주주총회 안건, 선임 내역과 사업목적 변경을 추출하는 규칙이다.

## 핵심 기능

### 주주총회 안건 추출

NOTICE·RESULT 형식의 안건을 같은 목록 구조로 만든다.

- 안건 원문은 확정한 이름의 바로 다음 `td`를 줄 단위로 읽고 빈 줄과 `-`를 제거한다.

- `제1호`, `안건`, `-제1`, `가.`, `나.`, `[`, `<`로 시작하는 줄은 새 안건으로 만들고 나머지는 앞 안건에 이어 붙인다.

- 결과는 `agendas`와 `agenda_items`에 저장한다.

### 주주총회 선임 내역

이사·사외이사·감사 선임 표를 구분해 저장한다.

- `이사선임 세부내역`, `사외이사선임 세부내역`, `감사선임 세부내역`은 각각 `director_elections`, `outside_director_elections`, `auditor_elections`에 저장한다.

- 세 목록은 위 순서로 `elections`에도 합친다. 성명이 비거나 `-`인 줄은 제외한다.

- 각 선임 항목에는 원래 표의 값과 `section_title`, `section_type`, `name`, `birth_month`, `term`, `is_new`, `is_full_time`, `major_career`, `other_company`를 넣는다.

### 사업목적 변경 추출

변경 전·후 내용과 일반 사업목적 내용을 구분한다.

- 사업목적 항목에는 `category`와 `reason`을 넣고 `구분`이 비었거나 `내용`이 `변경전` 또는 `내용`인 제목 줄은 제외한다.

- `business_purpose_changes` key는 결과에 항상 만든다.

### 주주총회 선택 항목 처리

NOTICE·RESULT의 실제 제목 변형과 선택적인 상세 목차를 구분한다.
