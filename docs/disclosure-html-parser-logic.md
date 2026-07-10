# 공시 HTML 파서 추출 로직

이 문서는 `공시원문 변환 / 모드별 기능`에서 HTML 구조에 직접 의존하는
추출 로직만 정리한다. 백엔드 mode 매핑, job 실행, 저장, 미리보기 로직은
제외한다.

## 요약

모든 보고서가 같은 방식으로 추출되지는 않는다.

| 모드 | 공통 table/span 처리 | 전용 상세 추출 | 방식 |
| --- | --- | --- | --- |
| `bond_issuance` 사채발행파싱 | 예 | 예 | 메인 사채 table 1개 선택 후 row 라벨 기반 추출 |
| `rights_issuance` 유무상증자파싱 | 예 | 예 | 필드 라벨/대상자 헤더 포함 조건을 만족한 table row를 합쳐 라벨 기반 추출 |
| `shareholder_meeting` 주주총회파싱 | 일부 | 예 | BeautifulSoup로 `td` 순서, `span` section title, 다음 table 기반 추출 |
| `asset_transaction` 유무형자산거래파싱 | 예 | 아니오 | 현재 공통 record만 생성 |
| `security_transaction` 발행증권거래파싱 | 예 | 아니오 | 현재 공통 record만 생성 |

## 공통 HTML 처리

관련 파일:

- `src/finiq/market_desk/web/html_parsers/common/metadata.py`
- `src/finiq/market_desk/web/html_parsers/common/tables.py`
- `src/finiq/market_desk/web/html_parsers/common/rows.py`

대부분의 웹 parser는 `build_base_record()`로 공통 record를 만든다.

공통 처리 흐름:

1. `document.xpath("//table")`로 모든 `<table>` 수집
2. `rowspan`/`colspan`을 논리 grid로 펼침
3. cell text를 뽑고 빈 값/연속 중복 값을 압축
4. 모드별 추출 대상 table/row를 결정
5. logical row에서 라벨과 값을 검색

주요 의존성:

- 추출 대상 정보가 `<table>` 안에 있어야 한다.
- 병합 셀을 텍스트 복사 방식으로 펼쳐도 의미가 보존되어야 한다.
- 빈 값과 연속 중복 제거가 값-라벨 관계를 깨지 않아야 한다.
- 모드별 추출 대상 table/row는 제외 단어보다 포함 조건을 우선해 정한다.
- 값은 대체로 라벨 오른쪽 또는 row 마지막 쪽에 있어야 한다.

주요 실패 가능성:

- table이 아닌 `div`/`p`/`span` 조합으로 값이 표현되는 경우
- nested table 때문에 문서 순서와 의미상 순서가 달라지는 경우
- 같은 라벨이 여러 table에 나와 첫 번째 match가 틀리는 경우
- row 마지막 값이 실제 값이 아니라 비고, 단위, 주석인 경우

## 사채발행파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/bond_issuance/__init__.py`
- `src/finiq/market_desk/web/html_parsers/bond_issuance/utils.py`
- `src/finiq/market_desk/web/html_parsers/bond_issuance/extractor.py`

처리 방식:

- 공통 `raw_tables`를 만든다.
- `사채의 종류`, `사채의 권면`, `자금조달의 목적`을 모두 포함한 첫 table을 메인 table로 선택한다.
- 선택된 table의 `logical_rows`에서 필드를 추출한다.

주요 추출 규칙:

| 출력 필드 | 현재 방식 | 리스크 |
| --- | --- | --- |
| `회차` | `사채의 종류` row에서 `회차` 오른쪽 값 | `회차`가 별도 row이면 실패 |
| `종류` | 제목에 `전환사채`/`교환사채`/`신주인수권부사채` 포함 여부 | 제목 표현이 다르면 실패 |
| `발행금액` | `사채의 권면` row 오른쪽에서 첫 숫자 | row 끝에 다른 숫자가 있으면 오추출 |
| `행사가액` | `전환가액`/`교환가액`/`행사가액` row의 마지막 숫자 | 숫자가 여러 개면 오추출 |
| `납입일` | label이 정확히 `납입일`인 row의 마지막 값 | 라벨 변형에 약함 |
| `만기일` | `사채만기일` row의 마지막 값 | 라벨 변형에 약함 |
| `행사시작일`/`행사종료일` | 행사 기간 row에서 `시작일`/`종료일` 기준 값 | 시작/종료 구조가 다르면 실패 |
| `투자자` | `발행 대상자명`, `발행권면` header table에서 row별 추출 | header 문구/금액 column 위치에 취약 |

핵심 리스크:

- 메인 table 선택이 고정 라벨 3개에 강하게 의존한다.
- 많은 필드가 "라벨 포함 row의 마지막 값" 또는 "마지막 숫자"에 의존한다.
- 같은 라벨이 여러 곳에 있으면 첫 matching row/table이 잘못 선택될 수 있다.

## 유무상증자파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/rights_issuance/__init__.py`
- `src/finiq/market_desk/web/html_parsers/rights_issuance/utils.py`
- `src/finiq/market_desk/web/html_parsers/rights_issuance/extractor.py`

처리 방식:

- 공통 table/span 처리 결과를 사용한다.
- 메인 table 하나가 아니라 증자 field 또는 section 조건을 만족하는 모든 table의 `logical_rows`를 합쳐 필드를 찾는다.
- 증자 유형은 공시 제목만으로 분류한다.

| 제목 포함 문구 | 분류 |
| --- | --- |
| `유무상증자` | `mixed` |
| `무상증자` | `bonus` |
| `유상증자` | `paid` |
| 없음 | `unknown` |

최종 record 구조:

| 분류 | flat 필드 의미 | 추가 상세 |
| --- | --- | --- |
| `paid` | 유상증자 본문 값 | `유상증자` 블록 |
| `bonus` | 무상증자 본문 값 | `무상증자` 블록 |
| `mixed` | `Ⅰ. 유상증자` 섹션 값 | `유상증자` 블록 + `Ⅱ. 무상증자` 이후의 `무상증자` 블록 |
| `unknown` | 기존 공통 라벨 추출 결과 | 상세 블록 없음 |

무상증자에서 구조적으로 존재하지 않는 `발행목적`, `발행가액`, `납입일`은
`field_parse_status`를 `not_applicable`로 둔다.

주요 추출 규칙:

| 출력 필드 | 현재 방식 | 리스크 |
| --- | --- | --- |
| `신주의 종류와 수` | `신주의 종류와 수` + `보통주식`/`기타주식` row의 마지막 숫자 | 주식 종류 라벨 변형에 약함 |
| `발행목적` | `자금조달의 목적` + 고정 목적 라벨 row의 마지막 숫자 | 목적 라벨 추가/변경 시 누락 |
| `발행가액` | 관련 row의 마지막 숫자 | 표 구조가 다르면 실패 |
| `증자방식` | `증자방식` row의 마지막 값 | row 끝 비고를 값으로 오해할 수 있음 |
| `납입일` | label이 정확히 `납입일`인 row의 마지막 값 | 라벨 변형에 약함 |
| `발행대상자` | `제3자배정 대상자`, `배정주식수` header table에서 추출 | header 문구/column 위치에 취약 |
| `발행대상자세부엔티티` | `명칭`, `대표이사`, `최대주주` header table에서 추출 | header가 2줄이면 취약 |

핵심 리스크:

- 여러 table row를 합쳐 검색하므로 같은 라벨이 여러 table에 있으면 잘못된 row가 선택될 수 있다.
- `보통주식`, `기타주식` 같은 고정 stock label에 의존한다.
- 제3자배정 대상자와 상세 엔티티는 header row 문구에 강하게 의존한다.

## 주주총회파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/shareholder_meeting/__init__.py`
- `src/finiq/data_scraper/parse/domain/shareholder_meeting.py`
- `src/finiq/data_scraper/parse/table_dict.py`

처리 방식:

- 웹 parser가 공통 `build_base_record()`로 `raw_tables`를 만든다.
- 상세 필드 추출은 `extract_shareholder_meeting_details()`에 위임한다.
- 상세 추출은 공통 logical row가 아니라 BeautifulSoup 기반이다.

안건 추출:

- 모든 `<td>`를 순회한다.
- `1. 결의사항`, `3. 의안 주요내용`, `결의사항`이 있는 td의 바로 다음 td를 값 cell로 본다.
- 값 text를 줄 단위로 나눈 뒤 안건 marker로 항목화한다.

세부내역 추출:

- `<span>` text가 section title과 정확히 같은지 찾는다.
- 해당 span 뒤의 첫 번째 `<table>`을 section table로 사용한다.
- 첫 row를 header로 쓰고, 중복 header는 `_1`, `_2` suffix를 붙인다.

대상 section:

| section title | 출력 분류 |
| --- | --- |
| `이사선임 세부내역` | `director` |
| `사외이사선임 세부내역` | `outside_director` |
| `감사선임 세부내역` | `auditor` |
| `사업목적 변경 세부내역` | business purpose changes |

핵심 리스크:

- 안건은 라벨 td와 값 td가 바로 이웃한다는 가정에 의존한다.
- 세부내역은 `<span>` 제목과 "그 다음 table" 구조에 의존한다.
- table 첫 row만 header로 쓰므로 다단 header에 취약하다.
- `사업목적 변경 세부내역`의 `내용_1`은 duplicate header 처리 결과에 의존한다.

## 유무형자산거래파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/asset_transaction/__init__.py`
- `src/finiq/market_desk/web/html_parsers/asset_transaction/extractor.py`
- `src/finiq/market_desk/web/html_parsers/asset_transaction/models.py`

현재는 `build_base_record()`로 공통 metadata, `raw_tables`, `raw_rows`만
생성한다. `AssetTransactionRecord().to_dict()`는 빈 dict를 반환하므로 상세
필드 추출은 없다.

## 발행증권거래파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/security_transaction/__init__.py`
- `src/finiq/market_desk/web/html_parsers/security_transaction/extractor.py`
- `src/finiq/market_desk/web/html_parsers/security_transaction/models.py`

현재는 `build_base_record()`로 공통 metadata, `raw_tables`, `raw_rows`만
생성한다. `SecurityTransactionRecord().to_dict()`는 빈 dict를 반환하므로 상세
필드 추출은 없다.
