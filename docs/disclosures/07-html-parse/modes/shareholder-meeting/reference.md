# Shareholder Meeting Parse Reference

## Paths

- `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/shareholder_meeting/parsed-shareholder_meeting.json`에 구조화 결과를 저장한다.
- 외부·내부 HTML 쌍을 받는 공개 parser는 외부 공시 제목을 호출 경계에서 canonical mode로 정규화하며 지원하지 않는 제목은 `ValueError`로 거부한다. 내부 HTML details helper의 mode가 없거나 유효하지 않으면 `unknown`이며 문서 구조나 다른 metadata로 보완하지 않는다.
- 필터 record의 `company_name`은 같은 공시를 파싱하기 전에 `reporting_company_name`으로 전달한다. 이 값은 명시적 현직기관의 보고회사 연결과 두 합병 당사자의 방향 판정에만 사용하며, 누락된 HTML field를 대신하는 fallback으로 사용하지 않는다.

### `<data_root>/07-converted/shareholder_meeting/parsed-shareholder_meeting.json`

#### I/O Structure

- 주주총회 단계·일자, 안건, 선임 내역, 문서-local 주체·관계와 사업목적 변경 record를 담은 출력 파일이다.
- `disclosure_phase`는 `notice`, `result`, `unknown` 중 하나다. `meeting_date`는 단계별 canonical 날짜 label이 붙은 첫 direct-row 값에서 읽은 `YYYY-MM-DD` 날짜다. 선택한 값이 유효하지 않아도 뒤 source로 바꾸지 않으며 `null`로 둔다.
- 회의 시각·장소, 기준일, 주주명부 폐쇄기간은 현재 별도 출력 key가 아니다.
- `agendas`와 `agenda_items`는 같은 안건 제목 문자열 배열이다.
- `agenda_records`는 행 순번 기반 `agenda_ref`, `number`, `title`, `resolution_type`, `candidate`, `result_raw`, `status`, `remarks`, `source`, `attributes`, `evidence`를 가진 객체 배열이다. 같은 의안 번호가 반복돼도 `agenda_ref`는 겹치지 않는다.
- 안건 source는 첫 유효 구조화 표 하나이며, 평면 표는 첫 줄의 `회의목적사항`을 제목 열로 고정한다. 그룹 header 표는 둘째 줄에 명시적인 `안건`이 있을 때만 그 열을 사용하고, 다른 열만 그룹화되었으면 첫 줄의 `회의목적사항`을 유지한다. 그 schema가 없을 때만 label 행의 직접 자식 셀 두 개를 쓰는 legacy 경로 하나를 사용하며, 어느 경로에서도 빈 행 값 때문에 다른 field·descendant·인접·다른 표 selector로 바꾸지 않는다.
- `elections`는 `director_elections`, `outside_director_elections`, `auditor_elections`, `audit_committee_elections`를 이 순서로 합친 배열이다.
- 선임 항목의 `section_type`은 `director`, `outside_director`, `auditor`, `audit_committee_member` 중 하나다.
- 이름이 명시된 선임 안건은 이름 증거와 직책 호환성을 한 번에 검사해 후보가 정확히 하나일 때만 선임 세부내역과 연결한다. 그 결과가 없을 때만 같은 직책의 선임 세부내역 한 건과 이름 없는 안건 한 건을 연결하는 유일한 의미 fallback을 허용한다. 안건 source의 structured→legacy 한 건과 합쳐 전체 허용 fallback은 두 개다.
- 선임 항목은 `major_career_lines`와 `other_company_lines`에 원문 `<br>` 경계를 보존한다. `other_company_lines`는 완전한 `기관+직위` 한 줄 또는 `기관명 줄+바로 다음 완전한 직위 줄` multiline statement로만 사용하며 역할 단어 내부에서 갈린 줄은 제외한다. 명시적 현재 경력에서 나온 `serves_at`은 evidence field를 `주요경력(현직포함)`으로 기록하고, 보고회사 자체이면 target을 `@reporting_company`로 사용한다. 직책 앞의 마지막 토큰이 부서명인 경우에는 그 앞의 법인명이 보고회사명과 정확히 일치할 때만 부서명을 분리한다.
- `entities`는 `entity_ref`, `entity_type`, `name`, `attributes`, 발견 위치인 `mentions`를 가진 객체 배열이다. `entity_type`은 source 문맥으로 정한 `person` 또는 `organization`이다.
- 사람 identity는 같은 문서의 전체 선임 행을 먼저 분류해 정한다. exact 이름에 nonempty `birth_month`가 없으면 birthless, 하나면 안건과 생년월 없는 선임 행도 그 값에 연결하고, 둘 이상이면 생년월 없는 표면은 제외한다. 명시적 생년월을 가진 행은 그 값을 유지하며 registry는 순차적인 same-name upgrade를 하지 않는다.
- `relationships`는 `source_ref`, `target_ref`, `relationship_type`, `attributes`, `evidence`를 가진 객체 배열이다. `relationship_type`은 `includes`, `candidate_for`, `elected_as`, `removed_from`, `resigned_from`, `subject_of`, `serves_at`, `external_auditor_of`, `shareholder_of`, `transferor_of`, `transferee_of`, `proposed_allottee_of`, `merger_target_of`, `acquisition_target_of`, `divestment_target_of` 중 하나다.
- 주주제안은 제안자보다 안건의 내용과 결과를 보존하는 데 초점을 둔다. 따라서 주주제안자와 `proposed` 관계는 만들지 않는다. 주식매수선택권도 안건은 `agenda_records`에 남기지만 개인별 부여 대상자, `subject_of(action=stock_option_grant)`, `option_granted_by` 관계는 만들지 않는다.
- `removed_from`과 `resigned_from`은 사람에서 `@reporting_company` 방향이며 RESULT에서 명시적으로 가결된 종료 안건만 만든다. 직책은 `attributes.office_type`, 단계와 상태는 `disclosure_phase=result`, `outcome=passed`로 저장한다.
- `external_auditor_of`는 회계법인에서 `@reporting_company` 방향이며 `attributes.state`를 `current` 또는 `former`로 저장한다. 전자투표 관리기관과 시스템 제공기관은 추출하지 않으며 `electronic_voting_manager_for`와 `electronic_voting_system_provider_for`는 지원 관계 유형이 아니다.
- `shareholder_of`, `transferor_of`, `transferee_of`, `proposed_allottee_of`, `merger_target_of`는 명시된 사람 또는 기관에서 `@reporting_company` 방향이다. `acquisition_target_of`와 `divestment_target_of`는 명시된 기관에서 해당 `agenda_ref` 방향이다.
- `@reporting_company`와 `@meeting`은 09단계에서 실제 node로 해석할 예약 참조다. 안건 관계는 `agenda_records[].agenda_ref`를 사용한다.
- `evidence`와 `mentions`에는 원문을 다시 찾을 수 있는 `section_title`, `table_index`, `row_index`, `field`, `raw_text`를 기록한다. 09단계로 전달하는 관계 evidence는 비어 있지 않은 `raw_text`를 반드시 가져야 하며, 좌표나 field만으로 대체하지 않는다.
- `business_purpose_changes`는 `category`, `reason`, `evidence`와 `before`·`after` 또는 `content`를 가진 객체 배열이다. `evidence`는 선택한 사업목적 표의 행과 `이유` field를 가리킨다.

#### Defaults and Exceptions

- `agendas`, `agenda_items`, `agenda_records`, `elections`, 네 역할별 선임 목록, `entities`, `relationships`, `business_purpose_changes`는 값이 없을 때 빈 목록이다.
- placeholder 성명은 `entities`와 관계에서 제외한다. 출생년월이 없는 유효한 영문 성명은 제외하지 않는다.
- 후보자 surface의 명시적 직책·선임 문구는 이름과 분리하고, 역할 문장만 있는 값은 사람으로 만들지 않는다.
- 07단계의 `entity_ref`는 해당 공시 안에서만 유효하다. 다른 공시와의 동일인·동일 기관 확정은 09단계의 보수적인 entity resolution 범위다.
- 안건 자유문의 의미 추출은 알려진 문장 구조에 한정되므로 명시된 모든 주체와 관계가 항상 추출된다고 보장하지 않는다.
- 안건별 표결 수치는 `attributes`의 원문 header와 값이며 통합 수치 schema나 전역 안건 분류를 보장하지 않는다.
- 거래 관계는 현재 참고사항 값 행, 선택된 안건, 파싱된 사업목적 변경 이유에 이름과 행위가 함께 있는 경우만 만든다. 무기명 역할이나 관련공시 링크에서는 주체를 추정하지 않는다.
