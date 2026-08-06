# 외부 HTML 저장 Cases

## 처리 계약

### 복구 동작

#### 외부 HTML 재시도

일시적인 요청 또는 저장 검증 실패로 생긴 누락을 줄인다.
- 실패한 공시만 기본 5회까지 다시 요청하고 재시도 뒤에도 실패한 접수번호는 최종 누락 목록에 남긴다.

#### 기존 외부 HTML 재사용

구조와 원본 해시가 그대로인 외부 HTML은 다시 받지 않는다.
- 현재 파일에서 계산한 값과 manifest에 기록된 `source_size_bytes`, `source_sha256`을 비교한다.

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

## 조건부 동작

### 외부 HTML 저장

- 원본 화면 전체는 압축 JSON에 복사하지 않고 연도별 HTML 파일로 보존한다.

### 외부 HTML 압축 record 구성

- 제목은 01단계 KIND 조건검색에서 받은 값만 쓴다. 외부 HTML에 있는 `<title>`이나 머리글로 보완하지 않는다.

### 외부 HTML 원본 검증 metadata 만들기

- 이 metadata는 문서 선택값을 건드리지 않고 저장 원본이 같은 파일인지 증명한다.

### HTML manifest metadata 연결

- `kind_disclosure_html_manifest.json`은 `acpt_no`가 같은 외부 HTML과 원본 공시 metadata를 연결한다.

### 압축 결과 무결성 확인

- worker가 반환한 `acpt_no` 집합에 중복·누락·추가 항목이 없는지 확인한다.

### 외부 HTML 표시 범위 제한

- 진행 내역과 오류 예시는 [공통 사양](../common/reference.md)을 따른다.
