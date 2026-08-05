# 외부 HTML 저장 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 자료 흐름

- 입력 경로는 `<data_root>/03-filter/<mode>/filtered.json`, 저장 경로는 `<data_root>/04-external-html-download/<mode>`이며 저장 형식은 아래와 같다.
```text
<data_root>/
├── 03-filter/
│   └── <mode>/filtered.json
└── 04-external-html-download/
    └── <mode>/
        ├── <year>/
        │   └── <acpt_no>.html
        ├── kind_disclosure_html_manifest.json
        └── compressed-external-html.json
```

## 처리 계약

### 정상 동작

#### 외부 HTML 저장

필터가 고른 공시에서 문서 선택 정보와 원본 식별값을 보존한다.
- 선택한 `<mode>/filtered.json`에 기록된 접수번호만 다운로드한다.
- 외부 HTML은 공시 연도와 접수번호를 사용해 `<year>/<acpt_no>.html`로 저장한다.
- 원본 화면 전체는 압축 JSON에 복사하지 않고 연도별 HTML 파일로 보존한다.
- 외부 HTML은 문서 선택 화면이므로 실제 내부 HTML은 내부 저장 단계에서 별도로 받는다.

#### 외부 HTML 압축 record 구성

공시와 문서를 식별하고 문서 선택 결과를 재현하는 정보만 JSON에 저장한다.
- `compressed-external-html.json`에는 필요한 식별 정보와 어떤 필터에서 선택됐는지 확인하는 정보를 저장한다.
- 압축 record에 넣을 `acpt_no`는 HTML 파일명에서 확장자를 뺀 값이다.
- 외부 화면에서 고른 본문 문서 번호는 `selected_main_doc_no`에 저장한다.
- 제목은 01단계 KIND 조건검색에서 받은 값만 쓴다. 외부 HTML에 있는 `<title>`이나 머리글로 보완하지 않는다.

#### 외부 HTML 원본 검증 metadata 만들기

압축 record가 가리키는 완료된 원본을 검증할 수 있게 한다.
- 외부 HTML을 모두 저장하면 원본마다 바이트 수를 `source_size_bytes`, SHA-256을 `source_sha256`에 기록한다.
- 두 값은 압축 record와 manifest에 함께 기록한다.
- 이 metadata는 문서 선택값을 건드리지 않고 저장 원본이 같은 파일인지 증명한다.

#### HTML manifest metadata 연결

저장한 외부 HTML이 요청한 원본 공시와 연결됐음을 manifest에 기록한다.
- 외부 HTML을 모두 저장하면 `acpt_no`가 같은 원본 공시 metadata를 연결해 `kind_disclosure_html_manifest.json`을 만든다.

#### 압축 결과 무결성 확인

요청한 HTML, worker 결과, 저장한 압축 JSON에 같은 접수번호 집합이 들어 있는지 확인한다.
- worker가 반환한 `acpt_no` 집합에 중복·누락·추가 항목이 없는지 확인한다.
- 압축 JSON을 저장한 뒤 파일, JSON 객체, `records` 목록과 `acpt_no` 집합을 다시 읽어 확인한다.

## 화면과 서비스 계약

### 정상 동작

#### 별도 경로 사용

저장 결과를 바꾸지 않고 표준 작업공간 밖에 외부 HTML과 압축 JSON을 저장하도록 요청한다.
- 출력 폴더를 따로 쓰려면 외부 HTML과 압축 JSON에 쓸 입력·출력 경로를 각각 지정한다.

#### 외부 HTML 표시 범위 제한

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
- 진행 내역과 오류 예시는 [공통 동작 문서](../common/behavior.md)를 따른다.
