# 본문 HTML 저장

## 기능 범위

- KIND 본문 HTML을 mode와 연도에 따라 나누어 저장한다.

## 자료 흐름

- 입력 경로는 `<data_root>/04-external-html-download/<mode>`, 저장 경로는 `<data_root>/05-internal-html-download/<mode>`이며, 저장 형식은 아래와 같다.
- 연도별 외부 HTML이나 `compressed-external-html.json`을 읽더라도 결과 HTML은 연도별로 저장한다.

```text
<data_root>/
├── 04-external-html-download/
│   └── <mode>/
│       ├── <year>/<acpt_no>.html
│       └── compressed-external-html.json
└── 05-internal-html-download/
    └── <mode>/
        ├── <year>/<acpt_no>.html
        └── kind_disclosure_html_manifest.json
```

## 처리 계약

### 정상 동작

#### 본문 문서 번호 기준

04단계가 확정한 본문 문서 번호를 그대로 다운로드 대상에 사용한다.
- 압축 JSON을 입력할 때는 `records[].selected_main_doc_no`만 본문 문서 번호 SoT로 사용한다.
- 연도별 외부 HTML을 직접 입력할 때도 `mainDoc`에서 직접 고른 문서 번호만 사용한다.

#### 내부 HTML 저장

선택한 공시에서 받은 KIND 본문 HTML을 원본 식별값과 함께 보존한다.
- 본문은 선택한 mode, 공시 연도와 접수번호를 사용해 `<mode>/<year>/<acpt_no>.html`로 저장한다.

#### 다운로드 대상 무결성 검사

요청 대상과 저장 결과에 같은 접수번호 집합이 들어 있는지 확인한다.
- 일반 실행에서는 중복·누락·추가 접수번호가 없는지 확인한다.
- 사용자가 작업을 취소하면 그 뒤 생긴 누락은 허용하되, 저장 항목이 중복되거나 추가됐는지는 계속 검사한다.

#### 내부 HTML manifest metadata 연결

검증을 마친 내부 HTML이 요청한 원본 공시와 연결됐음을 manifest에 기록한다.
- 다운로드 대상 무결성 검사를 통과한 HTML은 `acpt_no`를 원본 metadata와 연결해 `kind_disclosure_html_manifest.json`에 기록한다.
- 파일마다 바이트 수를 `source_size_bytes`, SHA-256을 `source_sha256`에 기록한다.
- manifest는 저장 HTML을 건드리지 않고 원본 연결과 완료 결과를 증명한다.

### 복구 동작

#### 기존 본문 HTML 재사용

구조와 원본 해시가 그대로인 본문 HTML은 다시 받지 않는다.
- HTML 식별 검사를 통과한 파일에서 바이트 수와 SHA-256을 계산해 manifest 기준값과 비교한다. 공통 재사용 규칙과 실제 확인 순서는 [공시분석 공통 사양](../common/reference.md)에서 확인한다.

### 중단 조건

#### 본문 식별값 오류가 나면 실패 처리

저장 경로와 다운로드 대상을 확정할 수 없는 본문을 저장하지 않는다.
- 압축 JSON에서 `records[]`가 객체가 아니거나 유효한 `acpt_no`가 없으면 실패 처리한다.
- 압축 JSON에서 `records[].selected_main_doc_no`가 비어 있거나, 연도별 외부 HTML에서 `mainDoc`으로 직접 고른 값이 없으면 실패 처리한다.
- 압축 JSON은 `records[].metadata.disclosed_at`에 적힌 ISO 날짜로만 저장 연도를 정한다. 이 값이 없거나 잘못되면 `records[].year`나 `acpt_no`로 대신하지 않고 실패 처리한다.
- 연도별 외부 HTML을 직접 입력하면 파일이 실제로 들어 있는 4자리 연도 폴더를 저장 연도로 사용한다.
- 압축 JSON에서 `records[].acpt_no`가 중복되면 실패 처리한다.

#### 다운로드 대상 검증을 통과하지 못하면 종료

요청 대상과 저장 결과가 다른 상태로 다음 단계에 진행하지 않는다.
- 일반 실행 결과에 중복·누락·추가 접수번호가 있으면 실패 처리한다.
- 사용자가 작업을 취소한 경우에도 저장 결과에 중복·추가 접수번호가 있으면 실패 처리한다.

#### 본문 검증을 통과하지 못하면 다운로드 중단

올바른 HTML만 결과로 남긴다.
- 새로 내려받은 본문이 HTML 판별 검사를 통과하지 못하면 방금 저장한 본문 파일을 삭제하고 실패 처리한다.

#### 내부 HTML manifest를 연결하지 못하면 종료

저장 HTML과 원본 공시를 연결하지 못한 결과를 다음 단계에 전달하지 않는다.
- 다운로드 대상을 검증한 뒤 저장된 `acpt_no`와 연결할 원본 metadata를 확정하지 못하거나 manifest를 저장하지 못하면 실패 처리한다.

## 화면과 서비스 계약

### 정상 동작

#### 내부 HTML 표시 범위 제한

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
- 진행 내역과 오류 예시는 [공통 화면 사양](../../common/common-ui/reference.md)를 따른다.
