# KIND 공시 식별자 규칙

작성일: 2026-07-02
최종 업데이트: 2026-07-11

## 결론

- KIND record의 기본 식별자는 `acpt_no`다.
- `acpt_no`는 입력 경로의 `Path.stem`, 즉 확장자를 제거한 파일명 전체이다.
- `_`를 기준으로 파일명을 자르거나 숫자 여부를 검사하는 대체 경로는 두지 않는다.
- KIND HTML parser는 DART `rcept_no` 필드를 생성하지 않는다. KIND↔DART 연결 workflow만
  별도 sidecar에 검증된 `rcept_no`를 저장한다.
- `doc_no`는 KIND viewer의 문서 선택용 식별자로만 사용한다.
- `compressed-external-html.json`의 `selected_main_doc_no`와 `docs`는 현재 record의 `doc_no` 산출과 정정 family 구성에 사용한다.
- 정정 family가 완성되면 record에는 `family_id`, `current_sequence`, `family_member_count`를 직접 저장하고, family 전체는 payload 최상위 `families`에 한 번만 저장한다.

## Source 역할

| Source | 역할 | 금지 사항 |
| --- | --- | --- |
| `filtered.json` | 회사명, 상장구분 보강 | `doc_no` source나 정정 family source로 보지 않음 |
| `compressed-external-html.json` | 현재 record의 `doc_no` 산출, `mainDoc` 기반 정정 family 보강 | `rcept_no` 생성에 쓰지 않음 |
| viewer `mainDoc` | viewer 안의 문서 선택 목록 | DART `rcept_no`로 해석하지 않음 |
| 입력 HTML 경로 | 파일명 전체에서 KIND `acpt_no` 생성 | `_` 앞 문자열이나 숫자 문자열만 선택하지 않음 |
| KIND HTML/viewer HTML | 공시 본문 | DART `rcept_no` 복원에 쓰지 않음 |
| OpenDART `corpCode.xml` | KIND 종목코드/회사명을 DART `corp_code`로 연결 | `rcept_no`로 해석하지 않음 |
| OpenDART `list.json` | DART `rcept_no`, 회사, 제목, 접수일, 제출인 매칭 증거 | DART 원문 HTML을 받지 않음 |

## 생성 규칙

- KIND `acpt_no`와 DART `rcept_no`는 같은 개념이 아니다.
- KIND base/parser record에는 `rcept_no`를 만들지 않는다.
- `filtered.json`, viewer HTML, `mainDoc`, `doc_no`에서 `rcept_no`를 추정하지 않는다.
- DART 연결 결과는 `<data_root>/01-list/dart-links`의 sidecar에만 둔다. 정상 날짜는
  `years/<year>.json`, 접수일이 잘못돼 연도를 정할 수 없는 미해결 record는
  `undated.json`에 분리한다.
- 생성한 `rcept_no`를 재귀적으로 제거하는 정리 단계도 두지 않는다.
- base record에는 빈 `correction_families`를 만들지 않는다.
- 정정 family 참조와 최상위 family는 외부 metadata에서 관계가 완성된 시점에 각각의 최종 위치에 직접 만든다.

## KIND↔DART 연결 상태

| 상태 | 의미 | `rcept_no` 저장 |
| --- | --- | --- |
| `matched` | 회사·접수일·제목·정정 여부 증거로 유일한 DART 공시임을 확인 | 저장 |
| `confirmed_absent` | `corp_code`를 확정하고 해당 회사·접수일 범위의 DART 목록을 끝까지 조회했지만 허용 범위에 후보 자체가 없음 | 저장하지 않음 |
| `unresolved` | 회사코드, 날짜, 제목 또는 후보 증거가 부족해 같은 공시를 증명하지 못함 | 저장하지 않음 |
| `ambiguous` | 유력한 DART 후보가 둘 이상이고 점수 차이가 충분하지 않음 | 저장하지 않음 |
| `lookup_failed` | DART API/network 응답을 끝까지 확인하지 못함 | 저장하지 않음 |

`confirmed_absent`는 “DART 소관이 아님”을 제목만 보고 추정한 상태가 아니다. DART 회사코드가
확정되고 완전한 목록 응답에서 날짜 후보가 없을 때만 사용한다. DART 후보가 있는데 제목
매칭에 실패한 경우는 반드시 `unresolved`다. `lookup_failed`도 부재로 바꾸지 않는다.

## 매칭 순서

1. KIND 6자리 `company_id`를 OpenDART `stock_code`와 연결한다.
2. 종목코드가 없으면 법인표기/공백을 정규화한 회사명 exact match를 보조로 사용한다.
3. 확정한 `corp_code`별 pending 접수일 범위로 `list.json` 전체 page를 조회한다.
   `last_reprt_at=N`으로 정정공시를 포함하고 날짜 허용 오차만큼 query bound를 확장한다.
4. 접수일, 정규화 제목, 정정 여부, 제출인을 비교한다.
5. 유일한 고신뢰 후보만 `matched`로 저장한다. DART 공시 HTML은 요청하지 않는다.

동일 KIND input fingerprint의 `matched`는 재사용한다. `confirmed_absent`는 DART에 이후
등록될 가능성을 고려해 기본 7일 뒤 다시 조회하며, 나머지 미확정 상태는 다음 실행에서
재조회한다. OpenDART 회사코드 목록도 기본 7일 cache하지만 API key는 cache/result에
기록하지 않는다.

## 판단과 검증 기준

- parsing 동작을 결정하는 실제 예시는 `resources/KIND/bond_issuance`와 `resources/KIND/rights_issuance` 아래 자료만 사용한다.
- 테스트 fixture와 합성 HTML은 이미 정한 계약의 회귀 여부만 확인하며 동작을 결정하는 근거로 사용하지 않는다.
