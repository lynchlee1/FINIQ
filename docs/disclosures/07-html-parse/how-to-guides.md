# parser 문제 조사하고 추출 규칙 고치기

## 1. 저장 결과 확인

사용자가 변환 오류를 제보하면 `<data_root>/07-converted/<mode>/parsed-<mode>.json`부터 확인한다.

- `records`: 다음 화면이 읽는 변환 결과
- `warnings`: parsing은 끝났지만 예상한 공시 양식과 다를 수 있는 파일과 이유
- `errors`: 변환에 실패한 파일과 Python 예외 유형·문장

실행 순서, 중간 저장과 취소 안내는 progress callback과 작업 상태로 전달하며 최종 JSON에는 저장하지 않는다. 변환에 성공한 record가 필터에서 빠져도 해당 warning은 최상위 `warnings`에 남긴다.

## 2. 실제 KIND 파일 확인

`bond_issuance`와 `rights_issuance`의 규칙은 `resources/KIND/bond_issuance`, `resources/KIND/rights_issuance`에 있는 실제 KIND 파일을 직접 확인해 결정한다.

## 3. 추출 규칙 변경

유형별 추출 규칙은 각 parser 진입점과 가까운 module에 둔다. 공통 HTML·표 처리는 `common` package를 사용한다.

test fixture와 합성 HTML은 실제 파일로 규칙을 확정한 뒤 회귀를 검증할 때만 사용한다.

저장 결과의 정확한 구조와 mode별 계약은 [공시원문 변환 사양](reference.md)에서 확인한다.
