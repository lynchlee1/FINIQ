# 외부 HTML 저장

## 목적

- 선택한 공시에서 KIND 외부 HTML을 받아 연도별로 저장한다.
- 외부 HTML에서 필요한 정보만 골라 JSON 파일 하나로 압축한다.

공시 자동화 04단계에서 외부 HTML 다운로드 경로를 정하고 실행한다.

## 핵심 기능

### 외부 HTML 저장

필터가 고른 공시에서 문서 선택 정보와 원본 식별값을 보존한다.

- 선택한 `<mode>/filtered.json`에 기록된 접수번호만 다운로드한다.

- 외부 HTML은 문서 선택 화면이므로 실제 내부 HTML은 내부 저장 단계에서 별도로 받는다.

### 외부 HTML 압축 record 구성

공시와 문서를 식별하고 문서 선택 결과를 재현하는 정보만 JSON에 저장한다.

- `compressed-external-html.json`에는 필요한 식별 정보와 어떤 필터에서 선택됐는지 확인하는 정보를 저장한다.

- 압축 record에 넣을 `acpt_no`는 HTML 파일명에서 확장자를 뺀 값이다.

- 외부 화면에서 고른 본문 문서 번호는 `selected_main_doc_no`에 저장한다.

### 외부 HTML 원본 검증 metadata 만들기

압축 record가 가리키는 완료된 원본을 검증할 수 있게 한다.

- 외부 HTML 원본마다 바이트 수는 `source_size_bytes`, SHA-256은 `source_sha256`에 기록한다.

- 두 값은 압축 record와 manifest에 함께 기록한다.

### HTML manifest metadata 연결

저장한 외부 HTML이 요청한 원본 공시와 연결됐음을 manifest에 기록한다.

### 압축 결과 무결성 확인

요청한 HTML, worker 결과, 저장한 압축 JSON에 같은 접수번호 집합이 들어 있는지 확인한다.

- 압축 JSON을 저장한 뒤 파일, JSON 객체, `records` 목록과 `acpt_no` 집합을 다시 읽어 확인한다.

## 사용과 화면

### 별도 경로 사용

저장 결과를 바꾸지 않고 표준 작업공간 밖에 외부 HTML과 압축 JSON을 저장하도록 요청한다.

- 출력 폴더를 따로 쓰려면 외부 HTML과 압축 JSON에 쓸 입력·출력 경로를 각각 지정한다.

### 외부 HTML 표시 범위 제한

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
