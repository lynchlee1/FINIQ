# 07 공시원문 변환

## 목적

목차 HTML과 외부 metadata를 읽어 선택한 파싱 방법의 구조화 결과를 저장하고 preview와 진단 정보를 제공한다.

공통 [참고 계약](reference.md)에서 실행 요청, metadata, 셀 표기, 저장 payload를 먼저 확인한다. 공시 유형별 추출 규칙과 전용 record 필드는 각 parser 문서가 소유한다.

## Parser 문서

- [자산 거래](parsers/asset-transaction.md)
- [채권 발행](parsers/bond-issuance.md)
- [유상·무상증자](parsers/rights-issuance.md)
- [증권 거래](parsers/security-transaction.md)
- [주주총회](parsers/shareholder-meeting.md)

## 단계 계약

### 연도별 parser 입력 수집

`parse_disclosure_html_payload()`가 참고 계약에 맞는 HTML과 metadata를 모으고 registry parser를 선택한다. 파생 필터는 상위 기본 필터의 06단계 HTML에 자식 멤버십을 적용한다.

#### 기본값과 예외

- `skip_errors`는 불리언으로 명시해야 하며 없거나 다른 형식이면 실패 처리한다.
- 확장자를 뺀 파일명이 같은 입력이 둘 이상이면 실행을 시작하지 않는다.
- 두 metadata 파일은 선택 입력이다. 사용할 파일의 `filtered_metadata_path`나 `compressed_metadata_path`를 각각 직접 지정해야 하며 인접 파일을 탐색하지 않는다.

### 공통 HTML 입력 변환

HTML을 공통 행 변환 규칙에 따라 `positional_rows`와 `logical_rows`로 바꾼다.

#### 기본값과 예외

- HTML·metadata 구조가 공통 입력 계약과 다르면 해당 결과를 만들지 않는다.
- 규격화된 `KIND 원본 없음` 빈 원문은 파일명의 접수번호와 파일 안의 접수번호가 같을 때만 업무 parser를 건너뛴다. 이때 `acpt_no`, 문서 번호, 누락 사유가 담긴 성공 record를 만들며 임의의 공시 값은 채우지 않는다.

### 선택한 mode parser 실행

`PARSER_REGISTRY`에서 선택한 parser가 공통 record에 업무값을 추가한다. 외부 title은 이를 받도록 선언한 parser에만 전달한다.

#### 기본값과 예외

- parser signature 검사나 파일 parsing이 실패하고 `skip_errors=False`이면 전체 실행을 중단하고 결과를 저장하지 않는다.

### metadata와 정정공시 묶음 연결

지정된 metadata를 파일명 stem 전체의 `acpt_no`로 연결한다. 필요한 구성원이 모두 있는 correction family만 만든다.

#### 기본값과 예외

- metadata·family index 구성이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

### 최종 payload 생성과 저장

성공 record, family, warning, error, 필터 조건과 실행 집계를 저장 결과 계약에 맞춰 JSON 하나로 게시한다.

#### 기본값과 예외

- 식별자 중복, 최종 payload 구성 실패 또는 저장 실패가 발생하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

### 파일별 parsing 오류 후 계속 처리

`skip_errors=True`이면 실패 파일의 일부 결과를 버리고 오류를 기록한 뒤 다음 파일을 처리한다. 같은 조건에서만 `progress_interval`마다 중간 결과를 저장한다.

#### 기본값과 예외

- 이 동작은 파일 단위 parsing 실패에만 적용하며 metadata·family index, 최종 payload 구성 또는 저장 실패에는 적용하지 않는다.

### warning 일관성 검증

parser warning의 수준·code·중복과 수준별 목록의 일치 여부를 최종 payload 구성 전에 검사한다.

#### 기본값과 예외

- 같은 warning 목록에 중복·빈 문장·수준 누락·복수 수준 지정이 있거나 두 목록이 일치하지 않으면 보정하지 않고 실패 처리한다.

### 변환 결과 미리보기

변환 결과와 원문 표 일부를 보여 주되 원본과 저장 결과는 바꾸지 않는다.

#### 기본값과 예외

- preview 입력 원문 하나라도 읽거나 변환하지 못하면 실패 처리한다.
- 변환 결과를 만든 뒤 부가 원문 표만 찾거나 읽지 못하면 이유를 표시하고 변환 결과는 유지한다.

### 필터 후보 생성

선택한 항목의 값별 전체 개수와 제한된 접수번호 예시를 계산하며 저장 결과는 바꾸지 않는다.

#### 기본값과 예외

- 원문 하나라도 실패하면 일부 후보를 반환하지 않는다.

### 변환 실행 제어와 검사

- `cancel_disclosure_html_parse()`가 실행 중인 변환에 취소 요청을 전달한다.
- `기존 데이터 검토`는 현재 설정과 입력 HTML로 임시 결과를 다시 계산하고 저장된 `parsed-<mode>.json` 전체와 비교한다.
- 수동 실행, 미리보기, 기존 데이터 검사와 실행 옵션 후보 조회는 같은 자식 `mode`와 선택적인 `parent_mode`를 사용하고, parser는 `parser_method`로만 고른다.
- 파생 필터를 선택하면 `mode`에는 자식 이름을, `parent_mode`에는 상위 기본 필터 이름을 전달한다. 변환 대상은 자식의 한 단계 파생 멤버십으로 제한한 뒤 `limit`을 적용한다.
- 기본 필터 결과는 `07-converted/<mode>`에, 파생 필터 결과는 `07-converted/<parent_mode>/subfilters/<mode>`에 저장해 같은 자식 이름을 사용하는 서로 다른 상위 필터의 결과가 충돌하지 않게 한다.
- `기존 데이터 검토`는 작업공간, 모드와 파싱 방법이 모두 선택된 뒤에만 실행할 수 있다. 필수 선택이 비어 있는 상태에서 검사 요청을 보내지 않는다.

#### 기본값과 예외

- 진행 알림 간격이 정수가 아니거나 1보다 작으면 실패 처리한다.
- 안내 수준, code, 접수번호나 예시 형식이 잘못되면 실패 처리한다.
- 파생 필터가 stale이거나 상위 HTML·metadata가 불완전하면 실패하며 다른 멤버십이나 HTML로 보완하지 않는다.

### parser 문제 조사

1. 제보받은 mode와 접수번호를 확인하고 같은 입력으로 변환을 다시 실행한다.
2. 저장 결과와 안내를 찾고 해당 06단계 HTML을 연다.
3. 기대값의 표와 칸을 현재 parser의 추출 규칙과 비교한다.
4. 해당 parser의 함수 책임을 확인해 규칙을 고치고 실제 원본, test fixture와 합성 HTML로 검증한다.
5. 변환을 다시 실행해 제보된 오류가 사라지고 다른 결과가 바뀌지 않았는지 확인한다.
