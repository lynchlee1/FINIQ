# 주주총회 관계

`relationships`는 다음 15개 관계를 사용한다.

| 관계 | 의미 |
| --- | --- |
| `includes` | 주주총회가 안건을 포함함 |
| `candidate_for` | 사람이 임원 후보로 올라감 |
| `elected_as` | 가결 결과에 따라 임원으로 선임됨 |
| `removed_from` | 가결 결과에 따라 직책에서 해임됨 |
| `resigned_from` | 가결 결과에 따라 직책에서 사임함 |
| `subject_of` | 사람이나 기관이 특정 안건의 대상임 |
| `serves_at` | 사람이 다른 회사에서 현재 근무함 |
| `external_auditor_of` | 회계법인이 보고회사의 외부감사인임 |
| `shareholder_of` | 사람이나 기관이 보고회사의 주주임 |
| `transferor_of` | 사람이나 기관이 주식 양도인임 |
| `transferee_of` | 사람이나 기관이 주식 양수인임 |
| `proposed_allottee_of` | 사람이나 기관이 제3자배정 대상임 |
| `merger_target_of` | 기관이 합병 대상임 |
| `acquisition_target_of` | 기관이 인수 안건의 대상임 |
| `divestment_target_of` | 기관이 양도 안건의 대상임 |

모든 관계에는 허용된 출발점과 도착점 유형, 문서 안에서만 유효한 참조값, 비어 있지 않은 원문 근거가 있어야 한다. 후보와 현재 임원은 구분한다. `elected_as`, `removed_from`, `resigned_from`은 결과공고에 `passed`가 명시된 경우에만 만든다.

임원 역할은 관계의 `attributes.office_type`에 `director`, `outside_director`, `auditor`, `audit_committee_member` 중 하나로 저장한다. 종료 관계는 사람에서 `@reporting_company` 방향이며 `disclosure_phase=result`, `outcome=passed`를 함께 기록한다. `external_auditor_of`도 회계법인에서 `@reporting_company` 방향이고 `attributes.state`는 `current` 또는 `former`다. `shareholder_of`, `transferor_of`, `transferee_of`, `proposed_allottee_of`, `merger_target_of`는 명시된 사람이나 기관에서 `@reporting_company`로 향한다. `acquisition_target_of`와 `divestment_target_of`는 명시된 기관에서 해당 `agenda_ref`로 향한다.
