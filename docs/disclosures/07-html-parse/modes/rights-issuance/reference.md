# Rights Issuance Parse Reference

## Paths

- `<data_root>/06-sections/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/rights_issuance/parsed-rights_issuance.json`에 구조화 결과를 저장한다.

### `<data_root>/07-converted/rights_issuance/parsed-rights_issuance.json`

#### I/O Structure

- 유상·무상·유무상증자 공통 record를 담은 출력 파일이다.
- `신주의 종류와 수`와 `증자 전 발행주식총수`는 보통주식·기타주식 항목을 항상 유지한다.
