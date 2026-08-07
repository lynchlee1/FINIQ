# 본문 HTML 저장

## 목적

- KIND 본문 HTML을 mode와 연도에 따라 나누어 저장한다.

공시 자동화 05단계에서 본문 HTML 저장을 실행한다.

## 핵심 기능

### 본문 문서 번호 기준

04단계가 확정한 본문 문서 번호를 그대로 다운로드 대상에 사용한다.

- 압축 JSON 입력의 본문 문서 번호 SoT는 `records[].selected_main_doc_no`다.

- 입력은 `compressed-external-html.json`만 허용한다.

- 결과 저장 연도의 SoT는 `records[].metadata.disclosed_at`이다.

### 내부 HTML 저장

선택한 공시에서 받은 KIND 본문 HTML을 원본 식별값과 함께 보존한다.

### 다운로드 대상 무결성 검사

요청 대상과 저장 결과에 같은 접수번호 집합이 들어 있는지 확인한다.

### 내부 HTML manifest metadata 연결

검증을 마친 내부 HTML이 요청한 원본 공시와 연결됐음을 manifest에 기록한다.

- 다운로드 대상 무결성 검사를 통과한 HTML은 `acpt_no`를 원본 metadata와 연결해 `kind_disclosure_html_manifest.json`에 기록한다.

- 파일마다 바이트 수를 `source_size_bytes`, SHA-256을 `source_sha256`에 기록한다.

## 사용과 화면

### 내부 HTML 표시 범위 제한

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
