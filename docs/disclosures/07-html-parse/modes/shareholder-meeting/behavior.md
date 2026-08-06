# 주주총회 변환 동작

## 자료 흐름

- HTML·metadata·최종 payload의 공통 계약은 [공시원문 변환 동작](../../common/behavior.md)을 따른다.
- 이 parser는 외부 `title`을 받지 않고 `field_parse_status`나 warning을 만들지 않는다.

## 처리 계약

### 정상 동작

#### 주주총회 안건 추출

NOTICE·RESULT 형식의 안건을 같은 목록 구조로 만든다.
- 안건 원문은 확정한 이름의 바로 다음 `td`를 줄 단위로 읽고 빈 줄과 `-`를 제거한다.
- `제1호`, `안건`, `-제1`, `가.`, `나.`, `[`, `<`로 시작하는 줄은 새 안건으로 만들고 나머지는 앞 안건에 이어 붙인다.
- 결과는 `agendas`와 `agenda_items`에 저장한다.

#### 주주총회 선임 내역

이사·사외이사·감사 선임 표를 구분해 저장한다.
- 선임·사업목적 표는 모든 `span` 중 정확히 같은 첫 목차 제목 뒤의 첫 표를 사용한다. 중복 제목에는 `_1`, `_2`, 빈 제목에는 `unknown`을 붙인다.
- `이사선임 세부내역`, `사외이사선임 세부내역`, `감사선임 세부내역`은 각각 `director_elections`, `outside_director_elections`, `auditor_elections`에 저장한다.
- 세 목록은 위 순서로 `elections`에도 합친다. 성명이 비거나 `-`인 줄은 제외한다.
- 각 선임 항목에는 원래 표의 값과 `section_title`, `section_type`, `name`, `birth_month`, `term`, `is_new`, `is_full_time`, `major_career`, `other_company`를 넣는다.

#### 사업목적 변경 추출

변경 전·후 내용과 일반 사업목적 내용을 구분한다.
- 사업목적 변경은 `구분=사업목적 변경`일 때 `내용`과 `내용_1`을 `before`·`after`, 나머지는 `content`로 저장한다.
- 사업목적 항목에는 `category`와 `reason`을 넣고 `구분`이 비었거나 `내용`이 `변경전` 또는 `내용`인 제목 줄은 제외한다.
- `business_purpose_changes` key는 결과에 항상 만든다.

#### 주주총회 선택 항목 처리

NOTICE·RESULT의 실제 제목 변형과 선택적인 상세 목차를 구분한다.
- mode가 `RESULT`이면 `1. 결의사항`, `NOTICE`이면 `3. 의안 주요내용` 또는 `결의사항`을 정해진 순서로 확인한다. mode가 없으면 두 유형을 모두 확인한다.
- 안건·선임·사업목적 목차나 유효 행이 없으면 해당 선택 목록을 빈 목록으로 저장한다.
