# Disclosure Graph Reference

## Paths

- `<data_root>/03-filter/<mode>/filtered.json`과 `<data_root>/07-converted/<mode>/parsed-<mode>.json`을 입력으로 받아 `<data_root>/09-disclosure-graph`에 `disclosure-graph.json`을 저장한다.

### `<data_root>/03-filter/<mode>/filtered.json`

#### I/O Structure

- 그래프 node에 연결할 회사·공시 metadata를 담은 입력 파일이다.

### `<data_root>/07-converted/<mode>/parsed-<mode>.json`

#### I/O Structure

- node와 edge로 바꿀 mode별 구조화 공시 결과를 담은 입력 파일이다.

#### Defaults and Exceptions

- 지원하는 `<mode>`는 `rights_issuance`, `bond_issuance`, `shareholder_meeting`이다.

### `<data_root>/09-disclosure-graph/disclosure-graph.json`

#### I/O Structure

- mode별 공시 결과를 node와 edge 집합 하나로 합친 출력 파일이다.
- `disclosure-graph.json`은 `finiq_disclosure_graph_v1` 형식을 쓰는 JSON 객체다.

**`format`** — 형식: string. 내용: `finiq_disclosure_graph_v1`

**`metadata`** — 형식: object. 내용: 만든 시각, mode별 입력 경로·처리/제외 건수, 검증 집계, 전체 node·edge 수

**`nodes`** — 형식: array. 내용: `id`, `label`, `type`, `group`, `tags`, `properties`를 가진 node

**`edges`** — 형식: array. 내용: `id`, `source`, `target`, `relation`, `category`, `weight`, `directed`, `properties`를 가진 edge

- node 유형은 회사, 사람, 기관, 발행 event, 증권, 자금 사용 목적, 주주총회, 의안이다.
- edge는 회사가 발행이나 주주총회를 실행한 관계, 발행 증권과 자금 목적, 투자자가 취득한 관계, 주주총회의 안건·후보·선임·제안·재직·선택권 부여 관계를 표현한다.
- edge마다 `properties.evidence`에 공시 제목, 접수번호, 공시일, 원본 경로, 추출 상세를 기록해 원문을 추적할 수 있게 한다.

#### Shareholder Meeting Resolution

- `@reporting_company`, `@meeting`, `agenda_ref`는 각각 필터 결과의 발행사 node, 해당 공시의 ShareholderMeeting node, 해당 공시 안의 Agenda node로 해석한다.
- ShareholderMeeting은 필터 결과의 canonical `company_id`, `company_name`, `disclosed_date`, `title`과 같은 `acpt_no`의 current 07단계 record 및 유효한 `meeting_date`가 모두 있을 때만 만든다. 누락 field를 legacy alias, parsed metadata, 기본 문자열 또는 공시일로 대체하지 않는다.
- ShareholderMeeting의 event 날짜는 07단계 `meeting_date`다.
- `includes`, `candidate_for`, `elected_as`, `removed_from`, `resigned_from`, `subject_of`, `serves_at`, `external_auditor_of`, `shareholder_of`, `transferor_of`, `transferee_of`, `proposed_allottee_of`, `merger_target_of`, `acquisition_target_of`, `divestment_target_of`는 각각 같은 이름의 대문자 edge로 저장한다.
- 주주총회 경로는 `PROPOSED`와 `OPTION_GRANTED_BY`를 지원하지 않는다. 주주제안 안건과 주식매수선택권 부여 안건은 Agenda node로 남지만, 제안자나 개인별 부여 대상자를 graph node·edge로 확장하지 않는다.
- 역할은 edge의 `properties.office_type`, 정규화한 안건 결과는 `properties`의 결과·상태 속성에 저장한다.
- NOTICE 후보 관계는 `CANDIDATE_FOR`이며 현재 재직 관계나 active 관계로 저장하지 않는다. `ELECTED_AS`와 `OPTION_GRANTED_BY`는 RESULT에서 명시적으로 가결된 관계이며 `ELECTED_AS`는 active 선임 관계다.
- `REMOVED_FROM`과 `RESIGNED_FROM`은 RESULT에서 명시적으로 가결된 종료 사실이며 `is_active=false`다. `meeting_date`를 `end_date`로 저장하고, 같은 Company·동일 person ID·동일 `office_type`의 더 이른 active `ELECTED_AS`만 같은 날짜에 종료한다. 동일일·미래 선임, 다른 직책, legacy 임원 edge는 종료하지 않는다.
- 출생년월 없는 종료 인물은 별도 신원으로 유지하며 이름만 같은 출생년월 보유 선임 인물로 재연결하지 않는다.
- `EXTERNAL_AUDITOR_OF`는 `state=current`이면 active, `state=former`이면 inactive다. 명시적 시작일이 없으므로 `start_date`는 비워 둔다. 전자투표 관리기관과 시스템 제공기관은 graph 대상에서 제외한다.
- `SHAREHOLDER_OF`는 `is_current=true`이면 active다. 거래 당사자·배정 대상·합병 대상·지분 인수 또는 양도 대상 edge는 거래 효력일을 별도로 추출하지 않았으면 `start_date`를 비워 둔다.
- 필터 record의 `has_later_correction`이 참이면 후속 정정 전 record는 node와 edge로 만들지 않는다.
- 사람 node는 발행사, 정규화 이름, 출생년월을 식별 범위로 사용한다. 출생년월이 없을 때는 발행사와 정규화 이름까지만 사용한다.
- 기관 node는 정규화 이름이 이미 수집한 상장회사와 일치할 때 Company로 합치고, 그렇지 않으면 Organization으로 유지한다.
- `SERVES_AT`의 source는 Person이고 target은 Organization 또는 Company다. 07단계 source가 `@reporting_company`를 target으로 지정하면 해당 보고 Company에 연결한다.
- 07단계의 표·행·field·원문 evidence는 graph edge의 `properties.evidence.details`에 포함한다.

#### Defaults and Exceptions

- 사람을 발행사 범위 밖의 동명이인과 합치지 않으며 이름 유사도만으로 사람이나 기관을 병합하지 않는다.
- 출생년월이 없는 사람은 같은 발행사 안의 같은 정규화 이름을 하나로 보기 때문에 해당 범위의 동명이인을 구분하지 못할 수 있다.
- ShareholderMeeting ID는 접수번호를 기준으로 만든다. 같은 회사·회의 날짜의 NOTICE와 RESULT가 별도 접수번호이면 별도 node로 유지한다.
- current filtered 필수 field나 유효한 07단계 `meeting_date`가 없거나, `agenda_records`, `entities`, `relationships` 중 하나라도 배열이 아닌 record는 graph input으로 사용하지 않는다. `company_key`, `submitter`, `disclosed_at`, parsed metadata, `agendas`, `elections`, `candidate_name` 같은 이전 field를 재해석하지 않으며 해당 JSON은 current pipeline으로 다시 생성해야 한다.
- `disclosure_phase`가 `notice` 또는 `result`가 아니면 빈 값으로 유지하며 공시 제목으로 추론하지 않는다.
- active 결과 관계의 유일한 graph 입력 계약은 `attributes.outcome="passed"`다. 이전 field나 원문 결과 별칭은 09단계에서 보완하지 않고 current 07단계 parser로 다시 생성한다.
- 예약 참조의 재정의, 중복되거나 entity와 agenda 사이에서 충돌하는 문서-local 참조, 관계 유형별 허용 source/target 유형을 어긴 관계는 graph에 넣지 않는다. 관계 evidence에는 비어 있지 않은 원문이 반드시 있어야 하며 좌표나 field 이름만 있는 값은 수용하지 않는다.
- 09단계는 07단계 문서-local 결과를 전역 graph 식별자로 해소하지만, 원문에서 누락된 자유문 의미를 다시 추출하지 않는다.
