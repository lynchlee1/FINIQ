# 07 변환 실행

## 연도별 parser 입력 수집

`parse_disclosure_html_payload()`가 [요청과 저장 계약](request.md)에 맞는 HTML과 metadata를 모으고 registry parser를 선택한다. 파생 필터는 상위 기본 필터의 06단계 HTML에 자식 멤버십을 적용한다.

### 제약과 분기

- 두 metadata 파일은 선택 입력이다. 사용할 파일의 `filtered_metadata_path`나 `compressed_metadata_path`를 각각 직접 지정해야 하며 인접 파일을 탐색하지 않는다.

### 중단 조건

- `skip_errors`는 불리언으로 명시해야 하며 없거나 다른 형식이면 실패 처리한다.
- 확장자를 뺀 파일명이 같은 입력이 둘 이상이면 실행을 시작하지 않는다.

## 공통 HTML 입력 변환

HTML을 공통 행 변환 규칙에 따라 `positional_rows`와 `logical_rows`로 바꾼다.

### 제약과 분기

- 규격화된 `KIND 원본 없음` 빈 원문은 파일명의 접수번호와 파일 안의 접수번호가 같을 때만 업무 parser를 건너뛴다. 이때 `acpt_no`, 문서 번호, 누락 사유가 담긴 성공 record를 만들며 임의의 공시 값은 채우지 않는다.

### 중단 조건

- HTML·metadata 구조가 공통 입력 계약과 다르면 해당 결과를 만들지 않는다.

## 선택한 mode parser 실행

`PARSER_REGISTRY`에서 선택한 parser가 공통 record에 업무값을 추가한다. 외부 title은 이를 받도록 선언한 parser에만 전달한다.

### 중단 조건

- parser signature 검사나 파일 parsing이 실패하고 `skip_errors=False`이면 전체 실행을 중단하고 결과를 저장하지 않는다.

## metadata와 정정공시 묶음 연결

지정된 metadata를 파일명 stem 전체의 `acpt_no`로 연결한다. 필요한 구성원이 모두 있는 correction family만 만든다.

### 중단 조건

- metadata·family index 구성이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

## 최종 payload 생성과 저장

성공 record, family, warning, error, 필터 조건과 실행 집계를 [저장 결과 계약](storage.md)에 맞춰 JSON 하나로 게시한다.

### 중단 조건

- 식별자 중복, 최종 payload 구성 실패 또는 저장 실패가 발생하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

## 파일별 parsing 오류 후 계속 처리

`skip_errors=True`이면 실패 파일의 일부 결과를 버리고 오류를 기록한 뒤 다음 파일을 처리한다. 같은 조건에서만 `progress_interval`마다 중간 결과를 저장한다.

### 제약과 분기

- 이 동작은 파일 단위 parsing 실패에만 적용하며 metadata·family index, 최종 payload 구성 또는 저장 실패에는 적용하지 않는다.

## warning 일관성 검증

parser warning의 수준·code·중복과 수준별 목록의 일치 여부를 최종 payload 구성 전에 검사한다.

### 중단 조건

- 같은 warning 목록에 중복·빈 문장·수준 누락·복수 수준 지정이 있거나 두 목록이 일치하지 않으면 보정하지 않고 실패 처리한다.
