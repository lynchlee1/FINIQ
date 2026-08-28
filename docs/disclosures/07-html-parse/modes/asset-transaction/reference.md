# Asset Transaction Parse Reference

## Paths

- `<data_root>/06-sections/asset_transaction/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/asset_transaction/parsed-asset_transaction.json`에 구조화 결과를 저장한다.

### `<data_root>/07-converted/asset_transaction/parsed-asset_transaction.json`

#### I/O Structure

- `asset_transaction` mode의 `acpt_no`, `mode`, 빈 `title`과 `상장구분`을 담은 출력 파일이다.
