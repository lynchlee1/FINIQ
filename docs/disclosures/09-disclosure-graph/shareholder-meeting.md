# 09 주주총회 관계

## 주주총회 참조값 해소

### 기본 노드와 참조 연결

- 07단계 `shareholder_meeting` record의 문서-local 참조를 graph node로 해석한다. `@reporting_company`는 필터 결과의 발행사, `@meeting`은 해당 공시의 주주총회 event, `agenda_ref`는 해당 공시의 안건 node에 연결한다.
- 필터 결과의 각 주주총회 공시를 기본 ShareholderMeeting node로 만들고, 같은 `acpt_no`의 07단계 record에 current schema의 `agenda_records`, `entities`, `relationships`가 모두 배열로 있을 때만 안건·주체·관계로 보강한다.
- `agenda_records`의 제목과 상태를 Agenda node에 저장하고 `includes`를 `INCLUDES` edge로 바꾼다.
- `candidate_for`, `elected_as`, `removed_from`, `resigned_from`, `subject_of`, `serves_at`, `external_auditor_of`, `shareholder_of`, `transferor_of`, `transferee_of`, `proposed_allottee_of`, `merger_target_of`, `acquisition_target_of`, `divestment_target_of`는 각각 같은 이름의 대문자 graph edge로 바꾸며 07단계의 역할·결과·상태 속성과 source evidence를 보존한다.

### 인물과 기관 식별

- 후보자 node는 발행사 범위의 정규화한 이름과 출생년월로 식별한다. 출생년월이 없는 사람은 발행사 범위의 정규화한 이름으로만 합친다.
- 문서-local 기관명이 수집한 상장회사 이름과 일치하면 기존 Company node에 연결하고, 그렇지 않으면 Organization node로 만든다.
- `serves_at`은 사람에서 외부 Organization 또는 Company 방향이다. 현직 기관이 보고 회사 자체로 명시되면 target은 `@reporting_company`가 가리키는 Company다.

### 날짜와 정정공시

- 주주총회 event 날짜는 current 07단계의 유효한 `meeting_date`만 사용한다.
- 필터 record가 `has_later_correction`으로 후속 정정 공시의 존재를 표시하면 그 이전 record는 current graph에서 제외한다.

### 선임과 제외 범위

- NOTICE의 `candidate_for`는 재직 관계로 바꾸거나 active로 표시하지 않는다. `elected_as`는 07단계가 RESULT의 명시적 가결로 만든 관계만 수용하고 active 선임 관계로 저장한다.
- 주주제안자와 주식매수선택권 부여 대상자는 07단계 추출 범위가 아니므로, 주주총회 graph도 `PROPOSED`와 `OPTION_GRANTED_BY` edge를 만들지 않는다. `PROPOSED_ALLOTTEE_OF`는 제3자배정 대상 관계이므로 이 제외 항목과 다르다.
- 전자투표 관리기관과 시스템 제공기관도 07단계 추출 범위가 아니므로 `ELECTRONIC_VOTING_MANAGER_FOR`와 `ELECTRONIC_VOTING_SYSTEM_PROVIDER_FOR` edge를 만들지 않는다. 외부감사인 `EXTERNAL_AUDITOR_OF`는 유지한다.

### 관계 종료와 시점

- `removed_from`과 `resigned_from`도 07단계가 RESULT의 명시적 가결로 만든 관계만 수용한다. 종료 edge 자체는 inactive이고 회의일을 `end_date`로 사용한다. 같은 회사·동일 person ID·동일 `office_type`의 더 이른 active `ELECTED_AS`만 그 날짜에 종료하며 동일일 또는 미래 선임은 닫지 않는다.
- 출생년월 없는 종료 인물은 별도 신원을 유지한다. 이름이 같다는 이유로 출생년월 보유 선임 인물이나 legacy 임원 edge에 다시 연결하지 않는다.
- `external_auditor_of`의 `state=current`와 `state=former`는 각각 active와 inactive로 저장하되, 원문이 감사계약 시작일을 말하지 않으면 회의일을 관계 시작일로 넣지 않는다. 전자투표 관리기관과 시스템 제공기관 관계의 시점은 07단계에서 읽은 회의일만 사용한다.
- 명시적 현재 최대주주 관계는 active로 저장한다. 주식 양도·양수, 제3자배정, 합병·지분 거래 관계는 원문에서 거래 효력일을 별도로 구조화하지 않으므로 주총일을 관계 시작일로 넣지 않는다.

### 입력 완전성과 schema

- 필터 record의 canonical `company_id`, `company_name`, `disclosed_date`, `title`과 같은 `acpt_no`의 current 07단계 record 및 유효한 `meeting_date`가 모두 있어야 총회 node와 관계를 만든다. 값이 없으면 `company_key`, `submitter`, `disclosed_at`, parsed title·source, 공시일 같은 대체 field나 날짜로 보완하지 않는다.
- `agenda_records`, `entities`, `relationships` 중 하나라도 배열이 아니면 해당 07단계 record를 semantic input으로 사용하지 않는다. `agendas`나 `elections` 같은 이전 schema field를 대신 읽지 않는다.
- `disclosure_phase`는 current 07단계 record의 `notice` 또는 `result`만 사용한다. 값이 없거나 유효하지 않아도 공시 제목으로 보완하지 않는다.
- active 결과 관계는 current 07단계가 `attributes.outcome="passed"`로 정규화한 값만 수용한다. `status`, `result`, `approved`, `가결`, `승인` 같은 대체 field나 원문 별칭을 graph 단계에서 다시 해석하지 않는다.
- 이전 schema로 만든 주주총회 parsed JSON은 graph 단계에서 호환 해석하지 않으며 current 07단계 parser로 다시 생성해야 한다.

### 인물과 기관 동일성

- 출생년월이 없거나 이름이 같은 사람을 발행사 범위를 넘어 전역 동일인으로 합치지 않는다.
- 출생년월이 없으면 같은 발행사 안의 같은 정규화 이름을 하나로 보기 때문에 그 범위의 동명이인을 구분하지 못할 수 있다.
- 기관명의 전역 해소도 정규화 이름이 수집한 회사와 일치하는 범위에 한정하며 유사한 이름을 추정 병합하지 않는다.

### 공시와 로컬 참조 범위

- ShareholderMeeting node는 접수번호별 공시 event다. 같은 회사와 회의 날짜를 가진 NOTICE와 RESULT라도 서로 다른 접수번호이면 자동으로 같은 총회에 병합하지 않는다.
- `@reporting_company`와 `@meeting`을 entity나 agenda가 다시 정의하거나 문서-local 참조가 중복·충돌하면 그 참조를 해소하지 않는다. 각 관계는 계약에 정한 source/target 주체 유형과 원문 위치를 특정할 수 있는 evidence가 모두 유효할 때만 edge로 만든다.
- 07단계에서 자유문 주체나 관계를 추출하지 못한 경우 09단계가 원문을 다시 해석해 보완하지 않는다.
