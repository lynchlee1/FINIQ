# Bond Issuance Parse Reference

## Paths

- `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/bond_issuance/parsed-bond_issuance.json`에 구조화 결과를 저장한다.

### `<data_root>/07-converted/bond_issuance/parsed-bond_issuance.json`

#### I/O Structure

- CB·EB·BW의 사채 조건, 자금조달 목적과 투자자 record를 담은 출력 파일이다.
- `발행목적`과 `투자자`는 `[[이름, 금액], ...]` 구조다.
- 전용 record field는 `corp_name`, `회차`, `종류`, `기업명(행사대상)`, `발행금액`, `발행목적`, `행사가액`, `납입일`, `만기일`, `사채발행방법`, `행사시작일`, `행사종료일`, `투자자`다.
- `corp_name`은 회사명 metadata가 있을 때만 포함한다.
- `발행금액`, `발행목적`과 `투자자`의 금액은 정수다. `행사가액`은 정수·실수 또는 `null`이고 날짜와 나머지 단일 값은 문자열 또는 `null`이다.
- `field_parse_status`는 모든 전용 업무 field에 `parsed`, `explicit_zero`, `source_not_found` 중 하나를 기록한다. `explicit_zero`는 `발행금액`과 `발행목적`에만 사용한다.
- 정해진 출처에서 값을 찾지 못했거나 title이 없으면 strong warning을 만든다. 발행목적 또는 투자자 합계가 발행금액과 다르면 weak warning을 만든다.
- warning code는 `bond_investor_table_missing`, `bond_funding_purpose_sum_mismatch`, `bond_investor_sum_mismatch` 또는 `source_not_found:<field>`다.

## Inspection Payload

- 사채 요약 조회는 원문 `input_directory`, 저장 결과 폴더와 선택 `limit`을 받아 주요 사채 field와 원문 preview를 반환한다.
