# 외부 HTML 저장

## 기능 범위

- 선택한 공시에서 KIND 외부 HTML을 받아 연도별로 저장한다.
- 외부 HTML에서 필요한 정보만 골라 JSON 파일 하나로 압축한다.

## 자료 흐름

- 입력 경로는 `<data_root>/03-filter/<mode>/filtered.json`, 저장 경로는 `<data_root>/04-external-html-download/<mode>`이며, 저장 형식은 아래와 같다.
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

### 복구 동작

#### 외부 HTML 재시도

일시적인 요청 또는 저장 검증 실패로 생긴 누락을 줄인다.
- 실패한 공시만 기본 5회까지 다시 요청하고, 재시도 뒤에도 실패한 접수번호는 최종 누락 목록에 남긴다.

#### 기존 외부 HTML 재사용

구조와 원본 해시가 그대로인 외부 HTML은 다시 받지 않는다.
- 현재 파일에서 계산한 값과 manifest에 기록된 `source_size_bytes`, `source_sha256`을 비교한다. 공통 재사용 규칙과 실제 확인 순서는 [공시분석 공통 사양](../common/reference.md)에서 확인한다.

### 중단 조건

#### 필터 입력 오류가 나면 실패 처리

다운로드 대상과 저장 연도를 입력에서 확정하지 못하면 실행하지 않는다.
- 선택한 `<data_root>/03-filter/<mode>/filtered.json`을 읽을 수 없거나 접수번호가 없으면 실패 처리한다.
- 입력값은 `format=kind_disclosure_filter_v1` 객체 맨 위에 있는 `disclosures` 목록만 허용한다.
- 각 항목은 숫자로 된 `acpt_no`를 가져야 하며 호환 field, 중첩 탐색과 중복 접수번호는 허용하지 않는다.
- 각 항목에 `disclosed_at`이 없거나 그 값이 유효한 ISO 날짜로 시작하지 않으면 접수번호에서 연도를 추론하지 않고 실패 처리한다.

#### 압축 record를 구성하지 못하면 종료

외부 HTML에서 압축 결과에 넣을 문서 식별값을 확정하지 못하면 불완전한 record를 만들지 않는다.
- 외부 HTML 안에 `acptNo`, `mainDoc`, `attachedDoc` 또는 각 select에 딸린 option 목록이 없으면 실패 처리한다.
- 외부 HTML에서 읽은 `acptNo`가 파일명과 다르면 실패 처리한다. 빈 `acptNo`를 파일명으로 대신하지 않는다.
- 문서 option 값이나 문서 번호가 비어 있으면 해당 option을 조용히 빼거나 불완전한 record를 저장하지 않고 실패 처리한다.
- 외부 HTML에서 선택한 본문 문서 번호를 찾지 못하면 05단계에서 쓸 수 없는 압축 record를 만들지 않고 실패 처리한다.

#### HTML manifest를 연결하지 못하면 종료

저장한 HTML에 연결할 원본 공시 metadata를 확정하지 못하면 manifest를 만들지 않는다.
- HTML manifest를 만들 때 저장한 접수번호와 같은 metadata가 없으면 실패 처리한다.

#### 압축 결과 검증을 통과하지 못하면 종료

일부 HTML이 빠지거나 다른 공시가 섞인 압축 JSON을 만들지 않는다.
- worker가 일부 HTML 결과를 반환하지 않거나 반환한 `acpt_no` 집합에 중복·누락·추가 항목이 있으면 실패 처리한다.
- 압축 JSON을 저장한 뒤 파일, JSON 객체, `records` 목록 또는 `acpt_no` 집합을 다시 검증할 수 없으면 실패 처리한다.

## 화면과 서비스 계약

### 정상 동작

#### 별도 경로 사용

저장 결과를 바꾸지 않고 표준 작업공간 밖에 외부 HTML과 압축 JSON을 저장하도록 요청한다.
- 출력 폴더를 따로 쓰려면 외부 HTML과 압축 JSON에 쓸 입력·출력 경로를 각각 지정한다.

#### 외부 HTML 표시 범위 제한

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
- 진행 내역과 오류 예시는 [공통 화면 사양](../../common/common-ui/reference.md)를 따른다.

### 복구 동작

#### 뷰어 metadata 일부 반환

일부 정보를 읽지 못해도 확인한 정보는 보여 준다.
- 회사명이나 종목 코드를 읽지 못하면 빈 값으로 둔다.
- 본문 문서번호나 제출일을 읽지 못해도 다른 값으로 대신하지 않는다.

### 중단 조건

#### 실행 입력 오류가 나면 중단

현재 요청 형식에 없는 입력은 사용하지 않는다.
- 다운로드 대상은 `data_root`와 `mode`로만 정한다.
- 압축할 폴더는 `input_directory`로만 받는다.
- 압축 worker 수는 `parallel_workers`로만 받는다.
