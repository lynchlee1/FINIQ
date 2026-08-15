# 주주총회 의미 추출 작업 Handoff (2026-08-14)

## 문서의 성격

이 문서는 주주총회 의미 추출 작업을 여기서 안전하게 마무리하고, 다음 세션에서 같은 실패를 반복하지 않도록 남기는 인계 기록이다. 구현 계약은 같은 디렉터리의 `features.md`와 `reference.md`를 기준으로 한다. 최종 검증 수치와 source hash는 **최종 freeze 뒤 갱신한 `PLANS.md`**에서 확인한다.

문서를 작성하는 동안에도 production 파일이 여러 차례 바뀌었다. 그래서 변하기 쉬운 최종 hash나 전체 추출 건수는 이 문서에 고정해 적지 않는다. 아래의 과거 감사 수치와 중간 테스트 결과는 당시 snapshot에만 유효하며, 최신 workspace의 완료 근거로 재사용해서는 안 된다.

## 목표와 현재 결론

목표는 주주총회 공시에서 안건, 후보자와 선임 결과, 제안자, 현직 관계, 전자투표 관계, 외부감사인, 임원 종료, 거래 당사자를 최대한 추출하면서 다음 원칙을 지키는 것이다.

- runtime은 완전히 deterministic이어야 한다.
- runtime에서 LLM, 네트워크 모델 호출, AI 판정 결과 조회를 사용하지 않는다.
- 원문에 없는 주체나 관계를 추정하지 않는다.
- source evidence와 문서-local 참조를 보존한다.
- fallback은 아래 두 종류로 제한하고 예외별 우회 경로를 쌓지 않는다.

현재 parser, semantic contract, stakeholder extractor, graph 소비 경로는 이 원칙에 맞춰 구현돼 있다. 실제 문서로 만든 golden corpus와 focused test도 갖췄다. 최종 freeze에서는 golden과 집중 테스트를 통과했고, 같은 immutable snapshot으로 2026년 4,389건 전수 감사까지 다시 마쳤다. 다만 마지막 코드 변경 뒤 2008–2026년 71,965건 전체 감사는 재실행하지 않았다. 정리하면 **현재 연도 구현과 회귀 자산은 인계할 수 있고, 최신 전체 이력 검증만 다음 세션에 남아 있는 상태**다.

## 시도 결과 요약

| 구분 | 결과 | 남길 원칙 |
| --- | --- | --- |
| 실제 원문 golden corpus와 AI adjudication 기록 | 성공 | runtime과 분리하고, 원문·판단 근거·negative boundary·hash를 함께 보존한다. |
| 안건·선임·제안·현직·투표·종료·거래의 19개 관계 계약 | 성공 | 명시적 source와 비어 있지 않은 원문 evidence만 사용한다. |
| fallback 축소 | 성공 | 구조화 안건 부재 시 legacy 1건, 이름 없는 유일 선임 연결 1건만 허용한다. |
| lookup·길이·metadata·뒤 source를 이용한 보정 | 실패 후 제거 | 누락값이나 해석 실패를 다른 field·DOM·graph 정보로 메우지 않는다. |
| 넓은 단어 포함 정규식 | 반복 실패 후 경계 강화 | positive 문법과 비슷한 negative 문법을 항상 한 쌍으로 검증한다. |
| 조건부 인접 줄 재조합 | 실패 후 명시 문법으로 교체 | 같은 canonical 셀의 전체 multiline 문법만 허용하고 역할 단어 분할은 제외한다. |
| 변경 중 snapshot의 전수 감사 재사용 | 실패 | 시작·종료·live hash가 모두 같은 immutable snapshot 결과만 현재 증거로 쓴다. |
| 최신 전체 이력 71,965건 감사 | 보류 | 현재 snapshot으로 다음 세션에서 새로 실행한다. 과거 snapshot 수치는 재사용하지 않는다. |

## 최종 검증 스냅샷

최종 production SHA-256은 다음과 같다.

- parser: `a5402f8194c82c4c15878660733c8894f5ac3fd5efc1f5ae16a249acd19f3ca3`
- semantics: `b1a221ba3e9b1c682930fc0b176b03a551693dcad0703b2eaffd4293ada0775b`
- stakeholders: `e32f90d251e702863a66dd9dfa04c886f348f15af50d7c16abcfee7e45793943`
- ontology: `c8f9ad46acdc4ff0f5583c65263d0db63b44c47bf0ac159bd5a4e0f0c8b40077`
- web entry: `08ba1e4c83772a2242560cb518bcecdb35382aeeec9242556e0e4a675c0e1270`

검증 결과는 다음과 같다.

- Golden: 34개 접수번호, 68개 전체 HTML, 1,478,272 bytes, `36 passed`
- 주주총회 6개 집중 suite: `501 passed, 1 skipped`
- ontology builder: `22 passed`
- 관련 KIND/web integration: `385 passed, 166 skipped`
- 전체 repository: `1358 passed, 167 skipped, 4 failed`; 실패 4건은 주주총회 범위 밖의 classification SQLite 계약 2건과 HTML download 입력 검증 순서 2건이다.
- 최종 2026년 전수 snapshot: external/internal 4,389쌍 모두 파싱, 예외와 hard invariant 위반 0건
- 최종 2026년 결과: 안건 29,911건, 선임행 9,565건, 주체 10,964건, 관계 56,412건, 사업목적 변경 2,316건
- 전수 report: `/private/tmp/finiq-handoff-final4-2026.ZFZ7p4/report.json` (SHA-256 `bf9316dc5a332f63b9a1d005aaba77acd29f7d73f614701e4c44b9c70865649d`)
- 같은 셀의 명시적 기관명·직위 줄바꿈 문법으로 78개 공시의 참양성 `serves_at` 92건을 복구했고, 역할 단어가 `사내\n이사`로 갈린 오탐 1건은 제거했다.
- 최종 fallback 정적 재감사에서는 외부감사인 action과 전자투표 기간 문법도 실패 후 rescue가 아닌 독립 후보 수집·union으로 정리됐으며, 위 두 허용 경로 외의 receipt별, metadata, 날짜, source, DOM, 직책, identity, evidence, decoder 대체 경로를 찾지 못했다.

최신 snapshot의 71,965건 전체 이력 감사는 실행하지 않았다. 테스트가 실패한 것은 아니며, 시간상 다음 세션에 남겨 둔 검증 과제다.

## 남겨진 검증 자산

### AI adjudicated golden corpus

`tests/fixtures/shareholder_meeting/golden`에는 34개 접수번호의 외부·내부 HTML 쌍, 즉 68개의 **전체 HTML 파일**이 있다. 잘라낸 snippet이 아니라 database 원본 전체를 byte-fixed fixture로 보존한 것이다.

- `manifest.json`은 각 fixture의 database origin, raw SHA-256, canonical parser output SHA-256과 positive/negative assertion을 기록한다.
- `adjudication.json`은 문서별 positive label, negative boundary, 판단 근거, disagreement와 resolution을 기록한다.
- `adjudication_prompt.md`는 사용한 판정 기준을 기록한다.
- fixture와 origin의 byte equality 및 raw SHA는 별도로 검사할 수 있다.
- 동일 입력을 두 번 파싱한 canonical JSON이 동일한지도 golden test가 검사한다.

이 corpus는 Codex multi-agent document adjudication으로 만들었다. 다만 repository에서 확인할 수 있는 정확한 hosted model 이름과 snapshot ID는 제공되지 않았다. `model_identity`에는 이 한계를 그대로 기록했으며, 임의의 모델명을 추정해서는 안 된다. AI는 기대값을 만들고 검토할 때만 사용했고 runtime LLM dependency는 없다.

Canonical output hash가 의미 정답을 대신하는 것은 아니다. 출력이 바뀌어 golden이 실패하면 구조화 결과와 assertion부터 원문에 대조해야 한다. 의미 회귀를 확인하지 않은 채 새 hash만 계산해 manifest에 넣는 **blind hash update는 금지**한다.

### 19개 관계 계약

현재 문서-local semantic contract는 다음 19개 관계 유형을 사용한다.

1. `includes`
2. `candidate_for`
3. `elected_as`
4. `removed_from`
5. `resigned_from`
6. `subject_of`
7. `proposed`
8. `serves_at`
9. `option_granted_by`
10. `external_auditor_of`
11. `electronic_voting_manager_for`
12. `electronic_voting_system_provider_for`
13. `shareholder_of`
14. `transferor_of`
15. `transferee_of`
16. `proposed_allottee_of`
17. `merger_target_of`
18. `acquisition_target_of`
19. `divestment_target_of`

모든 관계에는 계약된 source/target 유형과 문서-local ref, 비어 있지 않은 원문 evidence가 있어야 한다. 후보와 현재 재직 사실은 구분한다. `elected_as`, `option_granted_by`, `removed_from`, `resigned_from`은 RESULT에 명시적인 `passed` 결과가 있을 때만 허용한다.

## 구현된 경로

### 안건과 허용 fallback

기본 경로는 첫 번째 유효 structured agenda table 하나다. 제목 열은 schema를 선택할 때 고정한다. 행 값이 비어 있거나 예상과 다르더라도 다른 열·후손·인접 셀·다른 표로 바꾸거나 여러 표를 합치지 않는다.

목표로 허용한 fallback은 정확히 두 개다.

1. structured agenda schema 자체가 없을 때, 정확한 label과 같은 행의 direct child 두 셀만 읽는 `structured → legacy labeled cell` 전환
2. 이름으로 선임 상세와 안건을 연결하지 못했을 때, 같은 직책의 선임 상세가 정확히 한 건이고 이름 없는 호환 안건도 정확히 한 건인 경우의 `unique unnamed election` 연결

이 두 경로 외에는 field나 metadata 대체, 길이 기반 보정, lookup 기반 이름 교정, graph 단계의 원문 재해석을 새 fallback으로 추가하지 않는다.

### 정정공시 제안자

정정 비교 표의 direct child header가 정확히 `정정항목`, `정정전`, `정정후`이고, 참고사항 행의 권위 있는 `정정후` 문장이 후보 명단·직책·`주주제안(제안자|제안인: NAME)에 의한 후보자` 문법에 완전히 맞을 때만 제안자를 읽는다. 같은 이름이 해당 공시의 선임 상세에 있고 직책별 대상 안건을 하나로 확정할 수 있을 때만 `proposed`를 만든다.

`정정전`, 다른 정정항목, 비표준 header, 문장 일부만 비슷한 일반 안내는 제안자 source로 보지 않는다. 이 typed source는 안건 선택 실패를 메우는 fallback도 아니다.

### 주요 경력과 다른 법인

`other_company`는 다른 법인명과 직위가 명시된 source로 우선 사용한다. `major_career`는 `<br>`로 보존한 한 물리 줄이 현재 표식, 기관 표지, 허용 직위 문법을 모두 만족할 때만 `serves_at`으로 만든다. 과거 경력이나 학교·학과, 일반 전문직 문장, 여러 기관이 섞여 대상을 하나로 정할 수 없는 줄은 제외한다.

원문 기관명이 전달받은 `reporting_company_name`과 정확히 일치할 때만 보고회사 연결을 `@reporting_company`로 보낸다. 회사명을 모를 때는 부서명이나 다른 metadata로 보완하지 않는다.

### 전자투표와 외부감사인

정확한 현재 참고사항 value row에 이름과 행위가 함께 적힌 경우만 사용한다. 직접 위탁·위임이나 `관리기관: NAME`은 manager 관계로, 이번 총회의 긍정적 사용 선언·행사기간·기관명이 붙은 시스템 또는 서비스·기관 URL이 함께 있으면 provider 관계로 만든다.

일반 안내나 이용약관, URL 또는 시스템명만 있는 경우, 과거 사용이나 미사용·중단 문장은 현재 provider나 manager로 만들지 않는다. 같은 기관에 직접 관리 위탁 관계가 있으면 provider 관계도 중복 생성하지 않는다.

### 선임 종료와 lifecycle

직책과 이름이 직접 붙은 해임·사임 안건만 종료 대상으로 삼는다. parent 안건의 직책은 role이 없는 child 안건에 상속하지 않는다. `ROLE + 한국어 3음절 이름 + 의 + 해임·사임`과 영문·띄어쓴 이름의 명시 문법 밖에서는 trailing `의`를 이름 lookup이나 길이로 보정하지 않는다.

Graph에서는 RESULT·passed·유효한 회의일이 모두 있는 종료 edge만 사용한다. 같은 회사, 동일 person ID, 동일 `office_type`의 더 이른 active 선임이 정확히 맞을 때만 해당 edge를 종료한다. 이름만 같은 출생년월 보유 인물이나 다른 직책, 동일일·미래 선임, legacy 임원 edge에는 다시 연결하지 않는다.

### 거래 주체

현재 참고사항 value row와 선택된 안건, 이미 파싱한 사업목적 변경 이유에서 이름과 거래 행위가 직접 연결된 경우만 주주, 양도·양수인, 제3자배정 대상, 합병·인수·양도 대상을 만든다. 무기명 역할이나 관련공시 링크, 일반적인 M&A 설명은 주체 source로 쓰지 않는다.

합병은 방향을 확정할 수 있는 구조만 다룬다. 법인 표지가 붙은 단일 상대방, 명시적인 피합병·소멸 법인, 법인 표지가 붙은 흡수합병 대상, 보고회사가 정확히 한쪽인 두 당사자 문장이 여기에 해당한다. 취소·철회·중단·무산·백지화·폐기 문장은 현재 관계로 만들지 않는다.

### Graph 소비 계약

Graph는 current `agenda_records`, `entities`, `relationships` 배열만 사용한다. legacy `agendas`, `elections`, parsed metadata나 원문을 다시 해석해 빈자리를 메우지 않는다.

ShareholderMeeting을 만들려면 filtered record의 canonical `company_id`, `company_name`, `disclosed_date`, `title`, 같은 접수번호의 parsed record, 유효한 `meeting_date`가 모두 필요하다. 이를 `company_key`, `submitter`, `disclosed_at`, parsed title·source, 공시일로 대체하지 않는다. 예약 ref 충돌, 중복 local ref, endpoint 유형 불일치, 비어 있는 원문 evidence가 있는 graph edge는 제외한다.

## 이번 시도에서 드러난 실패와 교훈

### Grouped-header 가정으로 34개 안건 손실

두 줄 header가 있으면 둘째 줄의 특정 열을 항상 안건 제목으로 써야 한다고 넓게 가정했다. 그 결과, 실제로는 표결 수치 열만 그룹화된 RESULT 표에서도 제목 열을 잘못 해석해 안건 34개가 사라졌다. 둘째 header에 명시적인 `안건` 열이 있을 때만 그 열을 쓰고, 그렇지 않으면 첫 header의 `회의목적사항`을 유지해야 한다.

재발을 막으려면 두 종류의 실제 two-row header를 모두 golden 또는 reduced regression에 넣어야 한다. 안건 개수만 보지 말고 대표 번호·제목·상태도 assertion으로 고정한다.

### `재선임` prefix 처리로 후보자 7명 truncation

후보 표면에서 역할·행위 prefix를 제거하는 정규식의 경계가 지나치게 넓었다. 이 때문에 실제 후보자 7명의 이름 앞부분이 잘리는 회귀가 발생했다. `재선임` 같은 행위어는 독립된 명시 토큰일 때만 소비해야 하며, 사람 이름 내부나 경계가 불분명한 문자열에는 적용하면 안 된다.

후보 수 총계만으로는 이 문제를 발견하기 어렵다. 실제 접수번호별 후보 이름을 exact assertion으로 검사하고, 변경 전후의 entity/relationship 이름 diff까지 확인해야 한다.

### Trailing `의` lookup·length fallback

이름 끝의 `의`가 조사인지 이름 일부인지 가리려고 선임 상세표를 lookup하거나 이름 길이로 보정하는 방법을 시도했다. 하지만 이는 source와 무관한 lookup/length fallback이며, 동명이인과 실제 이름을 훼손할 수 있다. 이 경로는 허용하지 않는다.

현재는 종료 문장의 엄격한 문법 안에서만 `의`를 조사로 소비한다. 그 밖의 모호한 표면은 추출하지 않는다. 새 예외가 발견되더라도 이름 길이, 후보 목록 검색, 다른 field 대체를 차례로 덧붙여서는 안 된다.

### Graph metadata·date·identity fallback

초기 graph 경로에는 누락된 canonical field를 `company_key`, `submitter`, `disclosed_at`, parsed metadata, 기본 title 또는 공시일로 채우는 동작이 있었다. 종료 인물을 이름과 출생년월 존재 여부에 따라 다른 person ID로 다시 연결하기도 했다. 이런 동작은 graph가 parser 계약 밖의 의미를 재구성하게 만들고, 출처 없는 날짜와 신원을 생성한다.

재발을 막으려면 누락된 canonical input을 skip 또는 명시적 validation failure로 처리해야 한다. graph는 parser 원문을 재해석하지 않고, lifecycle reconciliation에서도 동일 person ID를 유지한다. 다른 mode의 legacy fallback과 주주총회 전용 경로를 혼동하지 않도록 주주총회 함수 범위의 테스트도 계속 유지한다.

### 근거·직책 대체 fallback

Graph가 관계 evidence의 원문 없이 표·행 좌표만으로 관계를 받아들이는 방법도 시도했다. 복수 후보의 직책을 세부내역에서 확정하지 못하면 안건 전체의 직책을 각 후보에게 대입하기도 했다. 전자는 관계를 뒷받침하는 결정적 원문을 잃고, 후자는 `이사 및 감사 선임` 같은 안건의 모든 후보에게 두 직책을 붙일 수 있다.

현재 계약은 관계 evidence에 비어 있지 않은 `raw_text`를 반드시 요구한다. 후보별 직책을 확정하지 못하면 `candidate_for`·`elected_as` 직책을 대신 만들지 않고, `subject_of`에도 불확실한 직책을 넣지 않는다. 좌표와 일반 안건 직책은 원문이나 후보별 직책을 대신할 수 없다.

### 조건부 인접 줄 재조합과 source 재탐색 fallback

coverage를 넓히려고 다음 방법을 구현했지만 모두 철회했다.

- direct 줄 해석이 실패한 경우에만 `other_company`의 기관명-only 줄과 뒤 직책-only 줄을 `pending` 상태로 재조합
- 회의일의 첫 canonical label 값이 미정·오형식이면 뒤 label·행·표에서 날짜 재탐색
- 첫 `기타 투자판단에 참고할 사항` 값이 비거나 해석되지 않으면 뒤의 같은 label 값까지 합침
- 첫 선임 section heading이나 legacy 안건 label의 schema가 맞지 않으면 뒤의 같은 heading·label을 재탐색
- `배정대상자` label 값이 비었을 때 다음 physical clause를 조건부 대체값으로 사용

모두 첫 source가 실패한 뒤 인접하거나 뒤에 있는 source를 다시 찾는 fallback이었다. 현재는 각 section의 첫 canonical occurrence와 물리 줄 경계를 고정한다. 회의일·참고사항·선임 section·legacy label은 처음 선택한 source가 유효하지 않아도 뒤 source로 바꾸지 않는다. `other_company`는 완전한 `기관+직위` 한 줄과, 같은 셀 안의 `기관명 줄+바로 다음 완전한 직위 줄`이 전체 문법에 맞는지를 각각 독립적으로 검사한다. 두 번째 문법은 direct parser의 실패 여부를 상태로 저장하지 않으며, `사내<br>이사`처럼 직책 단어 자체가 갈린 표면은 제외한다. 제3자배정의 inline·바로 다음 줄 표기도 하나의 anchored multiline 문법으로 명시한다. 값이 비었다고 별도 branch에서 다음 줄을 대체값으로 가져오지는 않는다.

이렇게 조건부 `pending` 재조합은 없애면서도, 실제 2026 문서에서 확인된 명시적 기관·직위 줄바꿈은 하나의 문법으로 보존했다. 다음에 recall을 넓힐 때도 `pending` 상태나 `find_next` rescue부터 되살리면 안 된다. 하나의 canonical source record와 완전한 문법으로 설명할 수 있는지 먼저 입증해야 한다.

### Overcapture 계열

다음 오탐 계열이 반복해서 발견됐다.

- provider: 일반 전자투표 안내, URL·시스템명·이용약관 일부, 과거 또는 부정 문맥을 현재 provider로 오인
- merger: 이름 없는 역할, 일반 M&A 문장, 취소된 합병, 복수 당사자의 방향이 불명확한 문장에서 기관을 생성
- proposer: 일반 `주주제안` 문구, 정정전·다른 정정항목, 불완전한 문장에서 제안자를 생성
- major career: 과거 경력, 학교·부서, 전문직 설명, 복수 기관이 섞인 줄을 현재 재직 관계로 생성

공통 원인은 특정 단어가 들어 있다는 사실만 관계의 근거로 삼거나, 빠진 요소를 다른 단서로 메운 데 있었다. 각 계열은 positive grammar뿐 아니라 겉보기에는 비슷해도 관계를 만들면 안 되는 negative boundary를 golden assertion에 함께 유지해야 한다.

### Hash drift와 전수 감사 무효화

2026년 및 2008–2026년 전수 감사를 마친 뒤 production 파일이 다시 바뀐 일이 여러 차례 있었다. 이전 snapshot에서 예외와 invariant가 0이었더라도 이후 hash의 코드를 검증한 것은 아니다. 변경 중인 snapshot으로 시작한 감사와 중단된 재감사는 폐기했으며, 최종 근거로 사용해서는 안 된다.

다음 감사에서는 시작 전에 대상 파일 hash를 두 번 확인한 뒤 immutable snapshot으로 복사한다. 종료할 때는 snapshot의 start/end hash가 같은지, live workspace hash도 freeze hash와 일치하는지 확인한다. 하나라도 다르면 결과와 aggregate count를 폐기하고, 코드가 안정된 뒤 처음부터 다시 실행한다.

특히 golden canonical hash가 달라졌다고 hash만 새 값으로 바꿔서는 안 된다. grouped-header 회귀 당시 네 golden 문서에서 안건과 관계가 대량으로 사라졌지만, 단순히 hash를 갱신하면 테스트만 다시 통과시킬 수 있었다. 올바른 절차는 이전·현재 semantic JSON을 비교하고 원문 assertion을 다시 확인한 뒤 parser를 고치는 것이었다.

### 단계식 문법을 fallback처럼 구현한 문제

여러 합법 문법을 지원하면서 첫 정규식이 실패할 때만 다음 정규식이나 인접 header를 검사하는 제어 흐름을 사용한 적이 있다. 결과가 맞더라도 `AGENTS.md`의 넓은 fallback 정의에서는 새 rescue 경로로 볼 수 있고, 문법 간 우선순위도 테스트하기 어려웠다.

이번에는 주식 양도 당사자, 외부감사인 전환, 사업목적 합병 상대방, 전자투표 위탁 문장을 독립 후보 수집과 명시적 중복 제거 방식으로 바꿨다. 외부감사인 action은 named 문장·인접 header·선언 문법에서 후보를 각각 모은 뒤 기존 action 우선순위를 적용한다. 전자투표 기간도 날짜 label 문법과 엄격한 상대기간 문법을 따로 계산해 union한다. 다음 작업에서도 `if A 실패 → B 시도`를 늘리기 전에 A와 B가 같은 canonical source를 해석하는 독립 문법인지 확인해야 한다. 그렇다면 fallback이 아니라 후보 수집으로 표현한다.

### 동일 인물 identity를 순차적으로 업그레이드한 문제

처음에는 안건에서 생년월이 없는 인물을 먼저 만든 뒤, 선임 상세표에 나온 같은 이름·생년월의 인물로 업그레이드하거나 병합했다. 이 방식은 순서에 의존하는 identity fallback이고 동명이인을 잘못 합칠 수 있어 제거했다. 그러자 `김한민`이 안건과 두 직책 상세에 함께 등장하는 실제 golden에서 birthless/birthful 중복 또는 agenda mention 누락 회귀가 바로 드러났다.

최종 방식에서는 registry가 기존 entity를 추측해 업그레이드하지 않는다. 안건 인물을 만들기 전에 해당 안건과 호환되는 직책들에서 같은 이름에 연결된 **고유한 생년월 값**을 계산한다. 직책이 둘이어도 생년월이 하나면 해당 canonical identity를 쓰고, 서로 다른 생년월이 둘 이상이면 모호하므로 연결하지 않는다. 이 경계는 `20260105000566` canonical golden과 별도 reduced semantic-contract test로 고정했다.

## 현재 보장과 미검증 범위

### 현재 repository가 표현하는 보장

- runtime parser와 graph에는 LLM 호출이 없다.
- 34개 실제 접수번호의 68개 full HTML golden provenance와 AI adjudication 기록이 있다.
- deterministic double parse, schema, ref, endpoint, evidence, phase/outcome와 positive/negative 의미 assertion을 검사하는 테스트가 있다.
- 19개 관계와 두 fallback 목표가 code·test·기능 문서에 표현돼 있다.
- correction proposer, major career, voting, termination, transaction, current graph 계약에 대한 reduced 및 실제 문서 회귀 테스트가 있다.
- 최종 production snapshot에서 2026년 4,389개 paired 문서를 모두 파싱했고 예외, 참조·evidence·endpoint·schema·중복·phase/outcome hard invariant 위반이 0건이었다.
- 같은 snapshot에서 줄바꿈 `other_company` 참양성 92건을 보존하고 역할 단어 분할 오탐을 제거한 사실을 문서별 diff로 확인했다.

이 항목들은 구현과 테스트 자산이 존재한다는 뜻이다. 문서 작성 뒤 코드가 바뀌면 최종 실행 결과를 다시 확인해야 한다. 최신 pass count와 production hash는 최종 freeze 후 `PLANS.md`에 기록한다.

### 아직 보장하지 않는 것

- 최신 production snapshot의 2008–2026년 전체 external/internal pairing, parse exception와 worker failure 0건
- 최신 전체 이력에서 schema, duplicate ref/relation, dangling ref, endpoint, raw evidence, NOTICE/RESULT lifecycle invariant 0건
- correction proposer와 parent-office 비상속 변경이 전체 이력에 미친 정확한 차이
- 자유문 의미의 절대적인 완전 추출; 현재 정책은 의도적으로 high-precision이며 모호한 문장은 제외한다.

과거 `PLANS.md`에 적힌 2026년 및 2008–2026년 aggregate는 당시 hash에서 나온 역사적 결과일 뿐이다. 최신 freeze 감사가 끝나기 전에는 현재 검증 결과처럼 표현하지 않는다. 이전 전체 repository 검사에서 확인한 classification SQLite 계약과 HTML download validation-order 실패는 주주총회 범위 밖의 known issue로 구분하되, 최종 전체 테스트에서 다시 확인한다.

## 다음 세션 실행 순서

1. 위 최종 production hash가 그대로인지 두 번 확인한 뒤 immutable snapshot을 만든다.
2. Golden 36건과 주주총회 집중 테스트를 짧은 freeze sanity check로 먼저 실행한다. Canonical hash가 다르면 출력의 의미를 비교하고, hash만 갱신하지 않는다.
3. 2008–2026년 71,965개 paired 문서를 같은 immutable harness로 감사한다. 연도별 paired/parsed/error/invariant와 관계별 aggregate를 보존한다.
4. Grouped two-row header, `재선임` 후보 이름, trailing `의`, correction-after proposer, 줄바꿈 `other_company`, provider·merger·proposer·major-career negative family를 전체 이력에서 별도 집계한다.
5. 감사 종료 때 snapshot start/end와 live-end hash를 비교한다. 불일치하면 해당 report를 폐기한다.
6. 전체 이력 감사가 통과하면 이 문서와 `PLANS.md`의 pending 항목만 갱신한다. 새로운 추출 규칙은 별도의 테스트·감사 주기로 분리한다.

그 다음 기능 개선은 별도 변경으로 다룬다.

- NOTICE와 RESULT의 동일한 물리 주주총회를 공시번호 밖에서 병합할지, 병합한다면 어떤 안정 키를 쓸지 설계한다.
- 현재 의도적으로 제외한 자유문 제안자, 암묵적 거래 상대방, 기관 표지가 없는 경력 문장의 recall을 원문 표본과 negative boundary로 먼저 조사한다.
- issuer-scoped person identity에서 회사 변경, 개명, 생년월 누락을 어떻게 표현할지 graph-level identity 정책을 별도로 설계한다.
- 주주총회 범위 밖의 전체 테스트 실패 4건은 classification SQLite 계약과 HTML download 입력 검증 순서 문제로 별도 task에서 해결한다.

## 마감 상태

이번 세션은 추출 규칙을 더 늘리지 않고 여기서 마감한다. 현재 2026년 범위와 집중 회귀는 통과했다. 다음 작업자는 전체 이력 감사부터 재개하면 된다. 기존 두 fallback 경계를 지키고, 새로 발견한 문제를 receipt별 예외로 처리해서는 안 된다. canonical source 계약이나 명시 문법의 일반 규칙으로 설명해야 한다. 최신 전체 이력 감사를 마치기 전에는 “전체 이력 검증 완료”라고 보고하지 않는다.

<!-- HUMANIZE-SUMMARY
원본/윤문본: 15,414자 → 15,578자
변경률: 6.09%

카테고리별 탐지(수동 검수, before → after)
- A 번역투·추상적 서술: 21 → 5
- D 상투적 결론·과장: 4 → 0
- E 문장 리듬 단조: 19 → 6
- F 명사 연쇄: 12 → 4
- H 접속·병렬 과다: 9 → 3
- I 간접 종결: 13 → 4

자체검증
1. 사실·주장·수치·날짜·고유명사 보존: 통과
2. 인용·코드·영어 약어 보존: 통과
3. 인수인계 문서 장르와 격식체 유지: 통과
4. 근거 없는 내용 추가·삭제 없음: 통과
5. 변경률 30% 이하: 통과
6. Markdown 구조·링크·표 보존: 통과

등급: B
사유: S1 잔존 없이 자체검증 6/6을 통과했으며, 긴 기술 문서의 정보 밀도와 계약 표현을 보존하기 위해 변경률을 낮게 유지했다.

주요 변경
- 첫 문단의 기준 문서를 두 문장으로 나눠 참조 관계를 명확히 함
- “결과는 맞더라도” 같은 긴 조건문을 짧게 나눠 판단 근거를 앞세움
- 반복되는 “재발 방지 원칙은”을 직접적인 실행 규칙으로 정리
- 영어 기술 용어는 유지하고 주변 조사·서술어만 자연스럽게 다듬음
-->

