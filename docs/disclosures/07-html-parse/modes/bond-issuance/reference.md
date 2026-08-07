# Bond Issuance Parse Reference

## Paths

- `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/bond_issuance/parsed-bond_issuance.json`에 구조화 결과를 저장한다.

### `<data_root>/07-converted/bond_issuance/parsed-bond_issuance.json`

#### I/O Structure

- CB·EB·BW의 사채 조건, 자금조달 목적과 투자자 record를 담은 출력 파일이다.
- `발행목적`과 `투자자`는 `[[이름, 금액], ...]` 구조다.
