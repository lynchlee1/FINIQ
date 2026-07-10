# KIND 공시 식별자 규칙

작성일: 2026-07-02
최종 업데이트: 2026-07-10

## 결론

- KIND record의 기본 식별자는 `acpt_no`다.
- `acpt_no`는 입력 경로의 `Path.stem`, 즉 확장자를 제거한 파일명 전체이다.
- `_`를 기준으로 파일명을 자르거나 숫자 여부를 검사하는 대체 경로는 두지 않는다.
- KIND HTML parser와 저장 workflow는 DART `rcept_no` 필드를 생성하지 않는다. `None` 자리도 만들지 않는다.
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

## 생성 규칙

- KIND `acpt_no`와 DART `rcept_no`는 같은 개념이 아니다.
- base record에는 `rcept_no`를 만들지 않는다.
- 외부 metadata 연결 단계에서도 `rcept_no`를 만들지 않는다.
- 생성한 `rcept_no`를 재귀적으로 제거하는 정리 단계도 두지 않는다.
- base record에는 빈 `correction_families`를 만들지 않는다.
- 정정 family 참조와 최상위 family는 외부 metadata에서 관계가 완성된 시점에 각각의 최종 위치에 직접 만든다.

## 판단과 검증 기준

- parsing 동작을 결정하는 실제 예시는 `resources/KIND/bond_issuance`와 `resources/KIND/rights_issuance` 아래 자료만 사용한다.
- 테스트 fixture와 합성 HTML은 이미 정한 계약의 회귀 여부만 확인하며 동작을 결정하는 근거로 사용하지 않는다.
