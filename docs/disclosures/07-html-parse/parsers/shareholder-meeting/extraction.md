# 주주총회 추출과 필드

## 추출하는 정보

| 항목 | 처리 방식 |
| --- | --- |
| 안건 | 열 구조가 분명한 구조화 안건(structured agenda)과 라벨 옆 셀을 읽는 구형 안건(legacy agenda)을 처리한다. |
| 임원 후보와 선임 결과 | 이사·사외이사·감사·감사위원 후보를 찾는다. 결과공고(RESULT)에서 가결된 경우에만 실제 선임 관계를 만든다. |
| 해임·사임 | 대상자와 직책을 기록하고, 가결된 결과는 그래프의 임원 재직 기간에도 반영한다. |
| 다른 회사의 현직 | 후보자의 주요 경력에서 현재 다른 법인과 직책이 명확할 때 재직 관계를 만든다. |
| 외부감사인 | 현재 감사기관과 변경 전 감사기관을 구분한다. |
| 주식 거래 당사자 | 주주, 주식 양도인·양수인, 제3자배정 대상자를 역할별로 구분한다. |
| 기업 거래 대상 | 합병·인수·양도의 상대 회사가 원문에 명시된 경우에만 연결한다. |
| 근거와 참조 | 문서 안에서만 유효한 주체, 참조값, 원문 근거를 보존하고 그래프 연결 대상의 유형을 검사한다. |

## 추출하지 않는 정보

다음 주체와 관계는 생성하지 않는다.

- 안건 중 **주주제안자**: 안건은 남기되 주체나 관계를 남기지 않는다.
- 안건 중 **주식매수선택권 대상자**: 안건은 남기되 주체나 관계를 남기지 않는다.
- 투표 중 **전자투표 관리기관** 및 **시스템 제공기관**: 주체나 관계를 남기지 않는다.

## 입출력과 필드 계약

`parse_shareholder_meeting()`은 `<data_root>/06-sections/shareholder_meeting/<YYYY>/<acpt_no>.html`을 입력으로 받아 공통 레코드에 `shareholder_meeting` 업무값을 추가하고, `<data_root>/07-converted/shareholder_meeting/parsed-shareholder-meeting.json`에 결과를 저장한다. 외부·내부 HTML 쌍을 받는 공개 파서는 외부 공시 제목을 호출 경계에서 `NOTICE` 또는 `RESULT`로 정규화하고, 지원하지 않는 제목은 `ValueError`로 거부한다. 내부 HTML 상세 파서를 직접 호출하면서 모드를 생략하거나 잘못 지정하면 `disclosure_phase=unknown`으로 유지한다. 문서 구조나 다른 메타데이터로 단계를 보완하지 않는다.

필터 레코드의 `company_name`은 파싱 전에 `reporting_company_name`으로 전달한다. 이 값은 명시적 현직 기관을 `@reporting_company`로 연결하거나 두 합병 당사자의 방향을 판정할 때만 쓴다. HTML의 누락 필드를 대신 채우는 값은 아니다.

| 필드 | 계약 |
| --- | --- |
| `disclosure_phase` | `notice`, `result`, `unknown` 중 하나 |
| `meeting_date` | 단계별 정규 날짜 라벨이 붙은 첫 직접 행에서 읽은 `YYYY-MM-DD`; 선택한 값이 잘못돼도 다른 행이나 공시일로 바꾸지 않고 `null`로 둠 |
| `agendas`, `agenda_items` | 같은 안건 제목 문자열 배열 |
| `agenda_records` | `agenda_ref`, `number`, `title`, `resolution_type`, `candidate`, `result_raw`, `status`, `remarks`, `source`, `attributes`, `evidence`를 가진 안건 배열 |
| 역할별 선임 목록 | `director_elections`, `outside_director_elections`, `auditor_elections`, `audit_committee_elections` |
| `elections` | 위 역할별 선임 목록을 적힌 순서대로 합친 배열 |
| `entities` | `entity_ref`, `entity_type`, `name`, `attributes`, `mentions`를 가진 문서 단위 주체 배열 |
| `relationships` | `source_ref`, `target_ref`, `relationship_type`, `attributes`, `evidence`를 가진 관계 배열 |
| `business_purpose_changes` | `category`, `reason`, `evidence`와 `before`·`after` 또는 `content`를 가진 배열 |

목록 필드는 값이 없을 때도 빈 목록으로 만든다. 회의 시각·장소, 기준일, 주주명부 폐쇄기간은 별도 출력 필드가 아니다. `agenda_ref`는 행 순번을 기준으로 문서 안에서 유일하며 같은 의안 번호가 반복돼도 겹치지 않는다. 안건 상태는 원문 결과와 비고가 명시한 경우에만 `passed`, `rejected`, `unresolved`, `withdrawn`, `not_tabled` 중 하나로 정규화한다. 제목에 `승인의 건`이 있어도 가결로 추론하지 않는다. 결과 표의 가결 여부, 찬성·반대·기권률과 비고는 원문에 있을 때 함께 읽되, 표결 수치는 원문 머리글과 값을 `attributes`에 보존할 뿐 통합 수치 스키마로 바꾸지 않는다. 안건도 전역 분류 체계로 추정하지 않는다.

선임 항목은 원래 표 값과 `section_title`, `section_type`, `name`, `birth_month`, `term`, `is_new`, `is_full_time`, `major_career`, `other_company`, 출처 근거를 가진다. `section_type`은 `director`, `outside_director`, `auditor`, `audit_committee_member` 중 하나다. 감사위원 표의 `사외이사여부`는 감사위원 역할 속성으로 유지하며, 같은 사람이 사외이사와 감사위원 표에 함께 나오면 한 문서 단위 사람에 두 역할을 연결할 수 있다. `major_career_lines`와 `other_company_lines`에는 원문의 `<br>` 경계를 보존한다.

`entity_type`은 원문 문맥으로 정한 `person` 또는 `organization`이다. `@reporting_company`와 `@meeting`은 09단계에서 실제 노드로 해석할 예약 참조이며, 안건 관계는 `agenda_records[].agenda_ref`를 쓴다. 07단계의 `entity_ref`는 해당 공시 안에서만 유효하다. 다른 공시와의 동일인·동일 기관 확정은 09단계의 보수적인 주체 해소 범위다. `evidence`와 `mentions`에는 원문을 다시 찾을 수 있도록 `section_title`, `table_index`, `row_index`, `field`, `raw_text`를 기록한다.
