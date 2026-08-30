# 공시 식별자

KIND와 DART의 모든 식별자는 로마자를 포함할 수 있는 텍스트다. 숫자로 변환하거나 숫자 형식으로 제한하지 않는다.

## KIND

- `company_id`는 회사 링크가 있는 공시에서 기업을 구분한다. 회사 링크가 없는 공시에는 `company_id`가 없을 수 있다.
- `acpt_no`와 `doc_no`는 문서를 구분한다.
- `company_cell_text`는 KIND 회사 칸의 원문 표시값이며 식별자가 아니다.

## DART

- `corp_code`와 `stock_code`는 기업을 구분한다.
- `rcept_no`는 문서를 구분한다.

## KIND·DART 식별자 연결

기업이나 공시 후보를 하나로 확정하지 못하면 연결을 만들지 않고 실패 처리한다.
