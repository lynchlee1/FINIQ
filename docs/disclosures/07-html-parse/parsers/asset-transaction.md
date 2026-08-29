# 자산 거래 공시 변환

`parse_asset_transaction()`은 `asset_transaction` mode의 유무형자산거래 공시에 공통 원본 표 변환을 적용한다. 공통 식별값은 남기고 mode 전용 schema는 빈 객체로 두며, mode 전용 업무값·`field_parse_status`·parser warning은 만들지 않는다. `raw_tables`는 preview와 parser 내부에서만 쓰고 최종 record에서 제거한다.

## 파일과 저장 형식

- `<data_root>/06-sections/asset_transaction/<YYYY>/<acpt_no>.html`을 입력으로 받아 `<data_root>/07-converted/asset_transaction/parsed-asset_transaction.json`에 구조화 결과를 저장한다.

- 출력은 `asset_transaction` mode의 `acpt_no`, `mode`, 빈 `title`과 `상장구분`을 담는다.
