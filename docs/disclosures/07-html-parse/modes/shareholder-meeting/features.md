# Shareholder Meeting Parse Features

## Purpose

`shareholder_meeting` mode로 주주총회의 단계와 일자, 안건, 선임 내역, 문서 안의 주체·관계와 사업목적 변경을 추출한다.

## Features

### Select the Shareholder Meeting Mode

#### Behavior

- `parse_shareholder_meeting()`이 `shareholder_meeting` mode의 업무값을 공통 record에 추가한다.
- 외부·내부 HTML 쌍을 받는 공개 parser는 외부 공시 제목을 한 번 `NOTICE` 또는 `RESULT` mode로 정규화하며 지원하지 않는 제목은 거부한다. 내부 HTML details helper를 직접 호출하면서 mode를 생략하거나 유효하지 않은 값을 주면 `disclosure_phase=unknown`으로 유지하고 내부 HTML 모양으로 보완하지 않는다.
- 필터 결과의 `company_name`을 파싱 전에 보고회사명으로 전달한다. 이 값은 명시적 현직 기관을 `@reporting_company`로 연결하고, 두 합병 당사자 중 반대편을 정확히 고르는 데만 사용한다.
- 단계별 canonical 날짜 label이 붙은 첫 direct-row 값을 source로 고정해 `meeting_date`를 읽는다. 그 값이 비었거나 유효한 날짜가 아니어도 뒤의 다른 label·행·표로 바꾸지 않고 `null`로 둔다.

#### Defaults and Exceptions

- 공시 제목만으로 안건 결과를 판정하지 않는다.
- 회의 날짜를 찾지 못해도 공시일을 회의 날짜로 간주하지 않는다.
- 회의 시각·장소, 기준일과 주주명부 폐쇄기간은 현재 전용 업무 key로 구조화하지 않는다.

### Parse Structured Agendas

#### Behavior

- 첫 줄 header에 `번호`와 `회의목적사항`이 있는 현재 안건 표를 기본 경로로 선택한다. 평면 표는 `회의목적사항`을 제목 열로 고정한다. 그룹 header 표는 둘째 header에 명시적인 `안건` 열이 있을 때만 그 열을 사용하고, 표결 수치처럼 다른 열만 그룹화된 표는 첫 줄의 `회의목적사항` 열을 유지한다. 행 값이 비어도 다른 제목 열로 바꾸지 않는다. 결과 표의 `가결여부`와 찬성·반대·기권률, 비고도 원문에 있을 때 함께 읽는다.
- 정정 전·후 비교 표는 기본 경로의 안건 표로 선택하지 않는다.
- 표의 각 안건은 문서 안에서 유일한 행 순번 기반 `agenda_ref`와 함께 `agenda_records`에 저장한다. 공시가 같은 번호를 여러 번 사용해도 서로 다른 안건으로 유지한다.
- `agenda_records`에는 `agenda_ref`, `number`, `title`, `resolution_type`, `candidate`, `result_raw`, `status`, `remarks`, `source`, `attributes`, `evidence`를 저장한다. 찬성률 같은 표별 수치는 `attributes`에 원문 header와 값으로 보존한다.
- 명시된 결과와 비고만으로 상태를 `passed`, `rejected`, `unresolved`, `withdrawn`, `not_tabled`로 정규화한다.
- 호환용 `agendas`와 `agenda_items`에는 같은 안건 제목 문자열 배열을 저장한다.

#### Defaults and Exceptions

- 제목에 `승인의 건`이 포함돼도 이를 가결로 추론하지 않는다.
- 결과가 없거나 정규화할 수 없으면 상태를 임의로 채우지 않는다.
- 표결 수치는 원문 header별 `attributes`로 보존하며 서로 다른 공시 형식을 하나의 수치 schema로 추정 변환하지 않는다. 안건 제목도 정관·배당·보수한도 같은 전역 taxonomy로 임의 분류하지 않는다.

### Parse Legacy Agenda Cells

#### Behavior

- 구조화 안건 표가 없을 때만 현재 표의 한 행에 직접 속한 두 셀을 사용한다. 첫 셀에서 앞 번호와 공백을 정규화한 값이 `결의사항`, `기타 결의사항`, `의안 주요내용` 중 하나와 정확히 일치할 때 둘째 셀을 안건 원문으로 읽는다. 하위 요소의 셀을 다시 탐색하지 않는다.
- `<br>`을 줄 경계로 보존하고 안건 번호·표식을 기준으로 레코드를 나눈다.

#### Defaults and Exceptions

- 정정항목·정정전·정정후를 담은 비교 표는 사용하지 않는다.
- 이 규칙이 유일한 안건 선택 fallback이다. 구조화 표가 선택된 뒤 다른 표나 값 칸으로 바꾸지 않는다.
- 유효한 표나 값 칸이 없거나 선택한 구조화 표의 안건 제목이 `-` 같은 placeholder뿐이면 `agendas`, `agenda_items`, `agenda_records`를 빈 목록으로 저장한다.

### Parse Election Details

#### Behavior

- 표 셀 안이 아닌 독립된 제목이 `이사선임 세부내역`, `사외이사선임 세부내역`, `감사선임 세부내역`, `감사위원선임 세부내역`과 일치하고 뒤 표의 header가 유효할 때 그 표를 읽는다.
- 결과를 각각 `director_elections`, `outside_director_elections`, `auditor_elections`, `audit_committee_elections`에 저장하고 이 순서로 `elections`에도 합친다.
- 각 항목에는 원래 표 값과 `section_title`, `section_type`, `name`, `birth_month`, `term`, `is_new`, `is_full_time`, `major_career`, `other_company`, 출처 근거를 넣는다.
- 감사위원 표의 `사외이사여부`는 감사위원 역할 속성으로 유지한다. 같은 사람이 사외이사와 감사위원 표에 있으면 하나의 문서-local 사람 주체에 두 역할을 연결할 수 있다.

#### Defaults and Exceptions

- 정정 비교 표의 셀에 들어 있는 목차 문자열은 독립된 제목으로 인정하지 않는다.
- 성명이 비었거나 `-`, 반복 header인 `성명`, `미정`, `미확정`, `후보자 미정`, `선임예정`, `해당사항 없음`인 줄은 사람으로 만들지 않는다.
- 유효한 독립 제목과 표를 찾지 못하면 해당 목록을 빈 목록으로 저장하며 header 모양만으로 다른 표를 대신 선택하지 않는다.
- 문서 전체의 허용 fallback은 두 개뿐이다. 첫째는 구조화 안건 schema 자체가 없을 때의 direct-cell legacy 안건 선택이고, 둘째는 이름으로 선임 안건을 연결하지 못했을 때 같은 직책의 선임 세부내역 한 건과 이름 없는 안건 한 건이 각각 정확히 하나인 경우의 연결이다. 후보자 문법은 canonical `candidate` field와 제목의 명시 문법을 독립적으로 수집·중복 제거하며, 다른 field나 DOM source로 대체하지 않는다.

### Extract Document-Local Entities and Relationships

#### Behavior

- 안건과 선임 표의 명시적 문맥에서 사람과 기관을 찾아 `entities`에 문서-local `entity_ref`, `entity_type`, 이름, 속성, 발견 위치인 `mentions`를 저장한다.
- 성명과 임원 후보자는 사람으로 분류한다. 이름 길이나 회사명 접미사만으로 사람과 기관을 서로 바꾸지 않는다.
- 주주제안에서는 누가 제안했는지보다 어떤 안건이 상정됐는지가 중요하므로, 주주제안자의 이름은 추출하지 않는다. 주식매수선택권도 부여 안건 자체만 보존하며 개인별 부여 대상자는 추출하지 않는다. 두 항목의 이름이 안건 제목, 후보자 열, 정정후 문장에 있어도 별도 `entity`나 `relationship`을 만들지 않는다.
- 사람을 만들기 전에 exact 이름 key별 선임표의 nonempty `birth_month` 집합을 계산한다. 값이 하나면 생년월이 없는 안건·선임 표면도 그 identity를 사용하고, 값이 둘 이상이면 생년월이 없는 표면은 모호하므로 연결하지 않으며, 명시된 생년월은 그대로 유지한다. 이미 만든 birthless 사람을 뒤에서 lookup하거나 upgrade하지 않는다.
- `relationships`에는 `source_ref`, `target_ref`, 소문자 `relationship_type`, 관계 속성, 출처 근거를 저장한다. 보고 회사와 회의는 각각 `@reporting_company`, `@meeting`으로 참조하고 안건은 `agenda_ref`로 참조한다.
- 관계 유형은 회의-안건 `includes`, 후보자-회사 `candidate_for`, 선임된 사람-회사 `elected_as`, 해임·사임한 사람-회사 `removed_from`·`resigned_from`, 안건 대상 `subject_of`, 사람-다른 기관 `serves_at`, 회계법인-회사 `external_auditor_of`를 사용한다.
- 이름이 원문에 직접 붙은 거래 문맥에서는 현재 최대주주 `shareholder_of`, 주식 양도·양수 당사자 `transferor_of`·`transferee_of`, 제3자배정 대상 `proposed_allottee_of`, 합병 대상 `merger_target_of`, 안건별 지분 인수·양도 대상 `acquisition_target_of`·`divestment_target_of`를 추가로 사용한다.
- 역할은 관계의 `attributes.office_type`에 `director`, `outside_director`, `auditor`, `audit_committee_member` 중 하나로 저장한다. 명시된 안건 결과는 정규화한 소문자 상태로 관계 속성에 전달한다.
- NOTICE의 후보자는 `candidate_for`로만 표현한다. RESULT에서 명시적으로 가결된 선임만 `elected_as`로 표현한다.
- 직책과 사람 이름이 직접 붙은 해임·사임 안건은 `subject_of.attributes.action`을 `removal` 또는 `resignation`으로 저장한다. RESULT에서 명시적으로 가결된 사람만 `removed_from` 또는 `resigned_from`으로 표현하며 NOTICE, 부결, 미결, 폐기 안건은 현재 종료 관계로 만들지 않는다.
- 선임 표의 `other_company`는 `<br>`별 완전한 `기관+직위` 줄 또는 같은 셀의 `기관명 줄 + 바로 다음 완전한 직위 줄`이라는 두 명시 문법으로 `serves_at`을 만든다. 후자는 두 줄 전체를 한 multiline statement로 검사하며, `사내<br>이사`처럼 역할 단어 자체가 갈린 표면은 기관으로 만들지 않는다. `주요경력(현직포함)`에서도 물리적인 한 줄 전체가 `현`·`現` 표식, 명시적 기관 표지, 허용 직위 문법에 정확히 맞을 때만 같은 관계를 만든다. 마지막 기관 토큰이 부서명이면 외부 기관으로 생성하지 않고, 부서명 앞의 법인명이 보고회사명과 정확히 같은 경우에만 `@reporting_company`로 연결한다. `other_company`에 같은 기관이 있으면 그 명시 필드를 우선한다.
- 첫 번째 정확한 `기타 투자판단에 참고할 사항` 제목 바로 다음 값 행 하나를 source로 고정해 이름과 행위가 함께 명시된 외부감사인을 추출한다. 선택한 값이 비거나 해석되지 않아도 뒤의 같은 제목으로 바꾸지 않는다. 이전 감사인과 현재 감사인은 `external_auditor_of.attributes.state`의 `former`, `current`로 구분한다.
- 전자투표 관리기관과 전자투표 시스템 제공기관은 중요한 분석 대상이 아니므로 추출하지 않는다. 위탁·위임 문장, 관리기관 선언, 시스템명, URL, 행사기간은 원문에 남지만 해당 기관의 `entity`나 `relationship`을 만들지 않는다.
- 같은 현재 값 행, 이미 선택한 안건 record, 이미 파싱한 사업목적 변경 이유에서만 이름이 명시된 거래 주체를 추출한다. RESULT 안건의 인수·양도 대상에는 안건 상태를 관계 속성으로 보존하고, `최대주주인 NAME`은 `maximum=true`인 현재 주주 관계로 함께 표현한다.
- 모든 주체와 관계의 출처 근거에는 section, field, 원문을 기록하고 표와 행 위치를 알 수 있는 source에는 그 위치도 기록한다. 09단계 관계로 쓰려면 비어 있지 않은 원문이 반드시 있어야 하며, 좌표만 있는 근거로 대체하지 않는다.

#### Defaults and Exceptions

- 영문 이름은 성명·후보자 문맥에 있으면 길이와 관계없이 사람으로 유지한다.
- 후보자 값 앞의 명시적 직책과 `선임의 건` 같은 행위 문구는 이름에서 분리한다. 직책·위원회 문장만 남고 실제 이름이 없으면 사람으로 만들지 않는다.
- 해임·사임의 직접 이름 문법만 종료 대상으로 사용한다. `전원 해임`의 괄호는 구분자로 나뉜 엄격한 사람 이름 명단일 때만 읽고 `주주제안 안건` 같은 설명은 사람으로 만들지 않는다. `ROLE + 한국어 3음절 이름 + 의 + 해임·사임`과 영문·띄어쓴 이름 뒤의 `의`만 조사 문법으로 소비하며, 다른 이름 표면은 선임 상세표나 길이 보정으로 바꾸지 않는다.
- `외 N인`의 N명이나 이름이 없는 일반 명사·회사 역할은 별도 주체로 추정하지 않는다.
- `major_career`의 평문 경력, 과거 `전`·`前` 경력, 교수·변호사처럼 기관과 허용 직위를 하나로 확정할 수 없는 줄은 `serves_at`으로 만들지 않는다. 부서명이 붙은 줄도 보고회사와의 정확 일치를 입증하지 못하면 제외한다.
- 이름 없는 `외부감사인 선임보고`에서는 기관을 추정하지 않는다. 전자투표 기관은 문구의 구체성이나 사용 여부와 관계없이 추출 범위에서 제외한다. 외부감사인 기관명의 오탈자와 약칭은 07단계에서 임의 교정하지 않는다.
- 이름 없는 `최대주주`, `매수인`, `양수인`, `상대방`, `M&A`, `합병계약 승인`은 주체로 만들지 않는다. 안건에서 법인 표지가 붙은 단일 상대방, `피합병법인`·`소멸법인` label, 법인 표지가 붙은 흡수합병 대상, 또는 양 당사자 중 보고회사가 정확히 한쪽인 합병 문장만 상대방을 확정한다. 관련공시 링크나 다른 문서에서 거래 상대방을 보충하지 않는다.
- 자유문 안건의 후보자 추출은 알려진 문장 구조에 한정되며 모든 표현을 완전하게 해석한다고 보장하지 않는다. 주주제안자와 주식매수선택권 부여 대상자는 자유문 표현과 관계없이 추출 범위에서 제외한다.

### Parse Business Purpose Changes

#### Behavior

- 독립된 `사업목적 변경 세부내역` 제목 뒤의 유효한 표를 사용한다.
- 사업목적 항목에는 `category`, `reason`과 선택한 표의 행·`이유` field를 가리키는 `evidence`를 넣고 `구분`이 비었거나 `내용`이 `변경전` 또는 `내용`인 제목 줄은 제외한다.
- `구분=사업목적 변경`이면 `내용`과 `내용_1`을 `before`·`after`, 나머지는 `content`로 저장한다.
- `business_purpose_changes` key는 항상 만든다.
- 사업목적 변경 이유에 법인 표지가 붙은 이름 바로 뒤의 흡수합병, 법인 표지 `NAME`과 조사 `와`·`과`·`와의`·`과의` 뒤의 소규모·간이합병, 단일 고유명사와 `와의`·`과의` 뒤의 합병, `날짜 합병 예정인 법인표지 NAME과의 합병`, 또는 `종속회사(NAME) 흡수합병`이 명시되면 그 이름을 `merger_target_of` 근거로도 사용한다.
- 같은 이유 field의 `피합병회사·피합병법인(NAME)`, `합병 후 소멸법인 NAME`, `합병완료된 (구)NAME`처럼 합병으로 목적·정관을 넘긴 법인이 명시된 구조도 합병 대상으로 사용한다. 복수 피합병회사는 괄호 안 전체가 법인 표지가 있는 이름 목록일 때만 나누고, 두 합병 당사자가 함께 나오면 사업목적을 넘겨받은 당사자가 문장 뒤에 정확히 반복될 때 반대편만 대상으로 정한다.
- 날짜·`소규모`·`간이` 같은 합병 수식어와 관계기업·사업부 같은 일반 역할은 이름으로 사용하지 않고, 이름 뒤 조사는 관계 문법에서 소비한다. 합병이나 목적·정관 반영이 취소·철회·중단·무산·백지화·폐기된 문장은 현재 합병 관계로 만들지 않는다.

#### Defaults and Exceptions

- 유효한 독립 제목과 표가 없으면 빈 목록을 저장한다.
- 이름 없는 `계열회사 흡수합병` 같은 역할 표현은 합병 대상 기관으로 만들지 않는다.
