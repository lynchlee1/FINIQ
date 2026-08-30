# HTML 재사용

## HTML 원본 연결과 재사용

저장한 HTML은 같은 `acpt_no`의 원본 공시와 manifest로 연결하고, 구조와 기준값을 검증해 재사용한다.

- 원본 JSON에서 같은 `acpt_no`의 공시를 찾아 manifest metadata로 사용한다. 찾지 못하면 manifest를 만들지 않고 요청 전체를 실패 처리한다.
- 구조 판별과 SHA-256 계산은 파일을 한 번 순차적으로 읽은 결과를 공유한다.

## 파생 필터의 HTML 재사용

파생 필터는 상위 기본 필터가 소유한 HTML과 manifest를 접수번호 부분집합으로 검증해 재사용하며 별도 출력을 만들지 않는다.

- 파생 필터가 stale이거나 `parent_result_fingerprint`가 현재 상위 결과와 다르거나, 상위 산출물이 없거나 미완료·손상 상태이면 실패 처리한다.
- 상위 폴더의 다른 파일은 대상 외로 보지 않는다. 부분집합에 원문이 없으면 미저장 건수로 보고하고, 손상·해시 불일치와 함께 재사용하지 않는다.
- 파생 필터 검사에서는 KIND를 다시 요청하지 않는다.

## HTML manifest

- 파일별 `source_size_bytes`와 `source_sha256`을 기록한다.
- `format`이 `finiq_disclosure_html_manifest_v2`인 manifest는 입력 JSON 전체의 `source_fingerprint`를 기록하지 않고 접수번호별 `source_sha256`로 재사용을 판정한다. 필터만 다시 실행했다는 이유로 기존 HTML을 무효화하지 않는다.
- `finiq_disclosure_html_manifest_v1`은 읽기만 지원하며, 이 형식에서만 `source_fingerprint`를 비교한다.

## 기존 HTML 기준 해시 만들기

기존 외부 HTML이나 본문 HTML에 바이트 수와 SHA-256 기준값이 없어 작업이 멈췄을 때 이 절차를 따른다.

1. 멈춘 단계가 `공시원문 외부 저장`인지 `공시원문 내부 저장`인지 확인한다.
2. 현재 HTML이 믿을 수 있는 원본인지 직접 확인한다.
3. 외부 HTML이면 `현재 외부 HTML 신뢰`, 본문 HTML이면 `현재 내부 HTML 신뢰` 체크박스를 고른다.
4. `기준 해시 생성`을 누르고 작업이 끝날 때까지 기다린다.
5. 작업이 끝나 화면에 저장 범위가 다시 표시되면 `기준 없음`이 0건이고 `해시 확인`이 기존 HTML 건수와 같은지 확인한다.
6. 다운로드 `실행`을 누르고 나머지 작업이 이어지는지 확인한다.
