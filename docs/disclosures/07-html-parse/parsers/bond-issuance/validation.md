# 채권 발행 검증

## 필드 상태

- 모든 업무값에 상태를 기록한다.
- `발행금액`이 0이나 `-`이면 `explicit_zero`로 기록한다.
- 발행목적에 양수 항목이 있으면 `parsed`, 숫자는 있지만 남길 항목이 없으면 `explicit_zero`, 숫자가 없으면 `source_not_found`다.
- 이 parser는 medium warning을 직접 만들지 않는다.

## 합계 검증

- 발행목적 합계나 투자자 합계가 발행금액과 다르면 허용 오차 없이 weak warning을 만든다.
- 합계가 달라도 원본에서 읽은 값은 고치지 않는다.

## 변환 결과 검사

- 조회 함수는 저장한 결과에서 사채 요약을 만든다.
- parser 문제는 06단계 HTML과 `resources/KIND/bond_issuance`의 실제 KIND 파일을 대조한다.
