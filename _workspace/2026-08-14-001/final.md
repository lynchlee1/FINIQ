# 주주총회 의미 추출 작업 결과 보고서

- 작성일: 2026-08-14
- 상태: 기능 구현·현재 연도 검증 완료, 전체 이력 재감사 인계
- 사례 HTML: [`examples-2026-08-14.html`](./examples-2026-08-14.html)
- 상세 인수인계: [`handoff-2026-08-14.md`](./handoff-2026-08-14.md)

## 1. 목적

주주총회 NOTICE와 RESULT HTML에서 안건과 사람·기관, 이들 사이의 관계를 결정론적으로 추출하는 것이 목표다. 후보자를 현직 임원으로 오인하지 않고, 이름 없는 주체를 추정하지 않으며, 파싱 실패를 다른 field·DOM·metadata로 메우지 않는 데 우선순위를 뒀다.

AI는 실제 원문을 바탕으로 golden 기대값을 판정하고 반례를 검토할 때만 사용했다. production runtime에는 LLM 호출이나 모델 의존성이 없다.

## 2. 이번에 구현·정리한 범위

- 구조화 안건과 direct-cell legacy 안건
- 이사·사외이사·감사·감사위원 후보와 선임 결과
- 후보자, 제안자, 주식매수선택권 대상자
- 해임·사임과 graph lifecycle
- 현재 다른 법인 재직 관계
- 외부감사인과 전자투표 manager/provider
- 주주, 양도·양수인, 제3자배정 대상자
- 합병·인수·양도 대상
- 문서-local entity/ref/evidence와 graph endpoint 계약
- 정정 비교표의 명시적 주주제안자

현재 semantic contract에는 19개 관계 유형이 있다. 세부 목록과 endpoint 계약은 상세 handoff와 같은 디렉터리의 `features.md`, `reference.md`에 기록했다.

## 3. 성공한 접근

### 실제 원문 golden corpus

- 34개 실제 접수번호
- 외부·내부 full HTML 68개, 총 1,478,272 bytes
- 원본 경로와 raw SHA-256, canonical output hash, positive/negative assertion 보존
- 문서별 AI adjudication 근거, disagreement와 resolution 보존
- 동일 입력의 반복 파싱 결정성 검사

Golden은 단순히 hash를 맞추는 승인 장치가 아니다. 출력이 달라지면 원문과 semantic diff부터 검토해야 한다. 의미를 확인하지 않은 채 manifest hash만 갱신해서는 안 된다.

### fallback 축소

파싱 실패 뒤 작동하는 fallback은 다음 두 개만 남겼다.

1. structured agenda schema가 없을 때 direct-child 두 셀의 legacy label source 사용
2. 이름으로 연결된 선임 안건이 0건일 때, 같은 직책의 선임 상세 한 건과 이름 없는 안건 한 건이 각각 유일한 경우 연결

주식 양도, 외부감사인, 사업목적 합병, 전자투표 위탁·행사기간의 여러 표현은 순차 rescue 대신 같은 canonical source에서 후보를 독립적으로 수집한 뒤 중복을 제거하도록 바꿨다.

### entity identity 사전 결정

생년월이 없는 사람을 나중에 같은 이름의 born entity로 업그레이드하던 순서 의존 병합은 제거했다. 이제 문서의 election row를 모두 먼저 읽고 exact person key별로 nonempty 생년월 집합을 만든다.

- 생년월 0개: birthless identity
- 생년월 1개: 그 birth identity
- 생년월 2개 이상: 생년월 없는 agenda/election 표면은 모호하므로 연결하지 않음
- 생년월이 명시된 election row: 명시값을 그대로 유지

이 규칙은 appointment, 일반 `agenda_candidate`, 생년월이 빈 election row에 똑같이 적용한다. registry의 사후 lookup이나 upgrade에 기대지 않으므로 입력 순서 때문에 인물이 합쳐지는 일도 없다.

### high-precision 경계

- `elected_as`, `removed_from`, `resigned_from`, `option_granted_by`는 RESULT의 명시적 passed에만 생성
- 관계 evidence에 비어 있지 않은 `raw_text` 필수
- major career는 현재 표식·기관·지원 직책이 모두 들어 있는 완전한 한 줄만 허용
- 같은 셀에서 기관명과 직책이 줄바꿈된 경우에는 완전한 multiline 문법을 만족할 때만 허용
- `사내\n이사`, `부\n회장`처럼 직책 단어 자체가 줄 중간에서 끊긴 표면은 제외
- 합병·전자투표·제안자에는 positive 문법과 cancellation·negation·generic-role 반례를 함께 유지
- graph는 current semantic arrays와 canonical filtered fields만 사용

## 4. 실패·철회한 접근과 교훈

| 시도 | 결과 | 교훈 |
| --- | --- | --- |
| grouped header면 항상 둘째 줄의 `안건` 열 사용 | 실제 golden 4건에서 안건 34개와 관계 소실 | 둘째 줄에 명시적 `안건`이 있을 때만 사용하고, 아니면 첫 줄의 `회의목적사항`을 유지한다. |
| `재선임`을 넓게 prefix로 소비 | 실제 인명 7개가 `이원재→이원`처럼 절단 | 행위어는 독립 토큰일 때만 소비하고 receipt별 exact 이름 diff를 검사한다. |
| trailing `의`를 이름 길이·선임표 lookup으로 보정 | 실제 이름 훼손과 source 간 fallback 위험 | 문장 문법이 명시한 조사만 소비하고 모호하면 추출하지 않는다. |
| birthless person을 나중에 unique born person으로 upgrade | 순서 의존·동명이인 오결합 위험 | registry에서 보정하지 말고 전체 문서의 immutable birth map으로 사전 결정한다. |
| graph에서 company/date/title/office/evidence 누락값 대체 | parser 밖 의미 재구성, 잘못된 endpoint·날짜 가능 | canonical input이 없으면 skip하고 graph는 원문을 재해석하지 않는다. |
| 첫 source 실패 뒤 다음 label·heading·row·clause 재탐색 | fallback 누적과 source evidence 불안정 | 첫 canonical source를 고정하거나 하나의 완전한 multiline production으로 표현한다. |
| 넓은 키워드 정규식으로 provider/merger/proposer/경력 추출 | generic 역할·부정·취소·복수기관 오탐 반복 | 명시적 결합 문법과 negative boundary를 같은 테스트에 둔다. |
| 변경 중인 worktree에서 전수 감사 | start/end/live hash drift로 결과 무효화 | immutable snapshot에서 실행하고 세 hash가 모두 일치할 때만 결과를 채택한다. |

구체 receipt와 반례 문장, 제거한 fallback 목록은 상세 handoff의 “이번 시도에서 드러난 실패와 교훈” 절에 남겼다.

## 5. 검증 결과

최종 수치는 현재 production hash를 고정한 뒤 이 절과 `PLANS.md`에 함께 기록한다.

- Golden: 36 tests, 34 receipts
- 주주총회 6개 suite: 501 passed, 1 skipped
- ontology builder: 22 passed
- KIND/web integration: 385 passed, 166 skipped
- 전체 repository 마지막 실행: 1,355 passed, 167 skipped, 4 failed

전체 repository에서 실패한 4건은 이번 주주총회 작업 범위 밖이다.

- classification SQLite contract 2건
- HTML download `max_workers` validation order 2건

최종 immutable 2026 audit에서는 4,389개 external/internal 쌍을 모두 파싱했다. exception과 hard invariant 위반은 0건이었다.

- 안건 29,911
- 선임행 9,565
- entity 10,964 (person 8,987 / organization 1,977)
- relationship 56,412
- business-purpose change 2,316
- report: `/private/tmp/finiq-handoff-final4-2026.ZFZ7p4/report.json`
- report SHA-256: `bf9316dc5a332f63b9a1d005aaba77acd29f7d73f614701e4c44b9c70865649d`

Snapshot의 start/end와 live-end에서 production hash가 모두 일치했다.

## 6. 현재 한계

- 최신 production을 기준으로 2008–2026년 71,965쌍 전체 이력 감사를 다시 완료하지 않았다.
- 자유문 의미를 모두 추출하지 않는다. 암묵적 거래 상대방, 모호한 경력, 알려지지 않은 제안자 표현은 의도적으로 제외한다.
- person identity는 공시 문서·보고회사 범위이며 전사적 인물 식별자가 아니다.
- NOTICE와 RESULT의 ShareholderMeeting은 접수번호별 노드이며 같은 물리 총회로 자동 병합하지 않는다.
- AI adjudication 기록에는 reviewer 역할과 판단이 남아 있지만, hosted model의 정확한 snapshot ID와 raw invocation transcript는 저장소만으로 독립 재현할 수 없다.

## 7. 다음 작업 순서

1. 문서에 기록된 production SHA-256을 두 번 확인한다.
2. immutable snapshot을 만든다.
3. Golden 36건과 focused suite를 먼저 실행한다.
4. 71,965 external/internal 쌍을 전수 감사한다.
5. parse exception, worker failure, ref/evidence/endpoint/duplicate/phase-outcome invariant를 연도별·관계별로 저장한다.
6. snapshot start/end와 live-end hash가 다르면 report를 폐기한다.
7. 통과한 경우에만 이 보고서와 `PLANS.md`의 pending 문구를 갱신한다.

기능 확장은 그 이후 별도 변경으로 진행한다. 우선순위는 NOTICE/RESULT meeting identity 설계, 모호하지 않은 자유문 recall 표본 조사, issuer 범위를 넘는 person identity 정책이다.

## 8. 마감 판정

현재 코드는 주주총회 범위의 focused/golden 계약과 최신 2026 immutable audit을 통과했다. 실패한 접근과 작업 재개 절차도 문서에 남겼다. 이 세션에서는 기능을 더 넓히지 않으며, 전체 71,965쌍 이력 검증은 다음 세션의 첫 작업으로 넘긴다.

<!-- HUMANIZE-SUMMARY
원본/윤문본: 5,423자 → 5,529자
변경률: 3.45%

카테고리별 탐지(수동 검수, before → after)
- A 번역투·추상적 서술: 8 → 2
- D 상투적 결론·과장: 2 → 0
- E 문장 리듬 단조: 7 → 2
- F 명사 연쇄: 5 → 2
- H 접속·병렬 과다: 4 → 1
- I 간접 종결: 5 → 1

자체검증
1. 사실·주장·수치·날짜·고유명사 보존: 통과
2. 인용·코드·영어 약어 보존: 통과
3. 리포트 장르와 격식체 유지: 통과
4. 근거 없는 내용 추가·삭제 없음: 통과
5. 변경률 30% 이하: 통과
6. Markdown 구조·링크·표 보존: 통과

등급: B
사유: S1 잔존 없이 자체검증 6/6을 통과했으며, 내용 보존을 우선해 변경률을 보수적으로 제한했다.

주요 변경
- “보완하지 않는 것을 우선했다” → “메우지 않는 데 우선순위를 뒀다”
- “단순 hash 승인 장치” → “단순히 hash를 맞추는 승인 장치”
- 긴 복문을 두 문장으로 나눠 검증 결과와 한계를 분명히 구분
- 기계적인 ‘~을 사용한다’ 반복을 직접적인 서술로 정리
-->

