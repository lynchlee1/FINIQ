# 공시원문 변환 핵심 추출 로직 리포트

이 문서는 `공시원문 변환 / 모드별 기능`에서 실제 HTML 구조에 의존하는 추출 로직만 정리한다.
백엔드 mode 매핑, job 실행, 저장, 미리보기 로직은 제외한다.

## 요약

모든 보고서가 완전히 같은 방식으로 추출되지는 않는다.

| 모드 | 공통 table/span 처리 사용 | 전용 상세 추출 있음 | 전용 방식 |
| --- | --- | --- | --- |
| `bond_issuance` 사채발행파싱 | 예 | 예 | 메인 사채 table 1개 선택 후 row 라벨 기반 추출 |
| `rights_issuance` 유무상증자파싱 | 예 | 예 | 정정 아닌 모든 table row를 합쳐 라벨 기반 추출 |
| `shareholder_meeting` 주주총회파싱 | 일부만 | 예 | BeautifulSoup 기반으로 td 순서, span section title, 다음 table 기반 추출 |
| `asset_transaction` 유무형자산거래파싱 | 예 | 아니오 | 현재 공통 record만 생성 |
| `security_transaction` 발행증권거래파싱 | 예 | 아니오 | 현재 공통 record만 생성 |

## 공통 HTML 의존 로직

대부분의 웹 parser는 먼저 `build_base_record()`를 통해 공통 record를 만든다.

관련 파일:

- `src/finiq/market_desk/web/html_parsers/common/metadata.py`
- `src/finiq/market_desk/web/html_parsers/common/tables.py`
- `src/finiq/market_desk/web/html_parsers/common/rows.py`

### 1. 모든 table 수집

`extract_tables()`는 `document.xpath("//table")`로 HTML 문서 안의 모든 `<table>`을 문서 순서대로 가져온다.

의존 가정:

- 추출 대상 정보가 HTML `<table>` 안에 있어야 한다.
- 화면상 표처럼 보여도 `div`, `p`, `span` 조합이면 공통 table 추출 대상이 아니다.
- wrapper table, layout table, nested table도 함께 잡힐 수 있다.

틀릴 수 있는 경우:

- KIND 양식이 table이 아닌 다른 마크업으로 구성된 경우
- nested table 때문에 문서 순서와 의미상 순서가 달라지는 경우
- 불필요한 table이 먼저 잡혀 이후 라벨 검색에 영향을 주는 경우

### 2. rowspan/colspan 해제

`expand_table()`은 각 `<tr>` 안의 `<th>`/`<td>`를 순회하면서 `rowspan`, `colspan`을 읽고 병합 셀을 논리 grid의 여러 칸에 복사한다.

의존 가정:

- `rowspan`, `colspan`을 텍스트 복사 방식으로 펼치면 화면상의 논리 표와 충분히 유사해진다.
- span 값이 없거나 잘못된 경우 `1`로 간주해도 된다.
- 같은 병합 셀이 차지하는 각 논리 위치에 같은 텍스트를 넣어도 후속 추출에 유리하다.

틀릴 수 있는 경우:

- 브라우저의 실제 table layout algorithm과 구현 결과가 다른 경우
- 깨진 HTML에서 span이 비정상적으로 겹치는 경우
- nested table의 내부 row까지 `.//tr`로 같이 잡히는 경우
- 병합 셀 복사로 생긴 반복 텍스트가 실제 데이터처럼 해석되는 경우

### 3. logical row 압축

span이 해제된 grid에서 cell text만 뽑은 뒤 `compress_repeated_texts()`가 빈 값과 연속 중복 값을 제거한다.

예상 형태:

```python
["1. 사채의 종류", "회차", "12", "종류", "전환사채"]
```

의존 가정:

- 빈 값은 추출에 필요 없다.
- 연속 중복 텍스트는 대부분 span 해제로 생긴 noise다.
- 열 좌표보다 row 안의 텍스트 순서가 중요하다.

틀릴 수 있는 경우:

- 같은 텍스트가 연속 반복되는 것 자체가 의미 있는 경우
- 열 위치가 중요한 표에서 압축으로 관계가 흐려지는 경우
- 중복 제거 후 `label 바로 오른쪽 값` 관계가 실제 HTML과 달라지는 경우

### 4. 정정표 제외

`is_correction_chapter()`는 table이 정정 공시 또는 정정 비교표인지 판단한다.

판단 기준:

- table 근처 chapter title에 `정정신고`가 있는지
- table text에 `정정사유`, `정정전`, `정정후`가 모두 있는지

의존 가정:

- 정정 비교표는 위 문구 조합으로 식별 가능하다.
- 정정표는 상세 필드 추출 대상에서 제외해야 한다.

틀릴 수 있는 경우:

- 실제 본문 table에 우연히 `정정사유`, `정정전`, `정정후`가 함께 있는 경우
- 정정 섹션 제목 구조가 달라서 chapter title을 못 잡는 경우
- 가장 가까운 이전 제목이 실제 table의 제목이 아닌 경우

### 5. row 기반 검색

`rows.py`의 유틸은 `logical_rows`를 대상으로 특정 문자열이 포함된 row를 찾는다.

주요 방식:

- `row_contains(row, *needles)`: row 전체 텍스트에 모든 검색어가 있는지 확인
- `row_containing(rows, *needles)`: 조건을 만족하는 첫 row 반환
- `row_with_label(rows, label)`: 번호를 제거한 셀 텍스트가 label과 정확히 같은 row 반환
- `value_after(row, label)`: 같은 row에서 label 바로 오른쪽 값을 반환
- `last_value(row)`: row의 마지막 값을 반환
- `last_int(row)`: row 오른쪽부터 숫자를 찾아 반환

의존 가정:

- 라벨 문구가 예상 문자열과 거의 같다.
- 값은 라벨의 오른쪽 또는 row의 마지막 쪽에 있다.
- 숫자 필드는 row 오른쪽부터 찾으면 원하는 값이 먼저 나온다.

틀릴 수 있는 경우:

- 라벨 문구가 바뀌는 경우
- 같은 라벨이 여러 번 나오는 경우
- row의 마지막 값이 실제 값이 아니라 비고, 단위, 주석인 경우
- 숫자가 여러 개 있는 row에서 마지막 숫자가 대상 값이 아닌 경우

## 1. 사채발행파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/bond_issuance/__init__.py`
- `src/finiq/market_desk/web/html_parsers/bond_issuance/utils.py`
- `src/finiq/market_desk/web/html_parsers/bond_issuance/extractor.py`

### 처리 개요

사채발행파싱은 공통 `raw_tables`를 만든 뒤, 그중 하나를 "사채 발행 주요 표"로 선택한다.
이후 `BondIssuanceExtractor`가 선택된 table의 `logical_rows`를 대상으로 필드를 추출한다.

### 메인 table 선택

`_main_bond_rows()`는 아래 3개 조건을 모두 만족하는 첫 번째 table을 메인 table로 본다.

| 필수 포함 라벨 |
| --- |
| `사채의 종류` |
| `사채의 권면` |
| `자금조달의 목적` |

의존 가정:

- 사채 발행 결정의 핵심 정보는 하나의 table 안에 있다.
- 위 3개 라벨은 사채 발행 주요 표에 항상 존재한다.
- 첫 번째 매칭 table이 실제 메인 table이다.

틀릴 수 있는 경우:

- `사채권면총액`, `권면총액`, `조달목적`처럼 라벨이 다르게 표현되는 경우
- 주요 정보가 여러 table에 나뉘어 있는 경우
- 같은 라벨을 포함한 요약/비교 table이 먼저 나오는 경우

### 필드별 추출 규칙

| 출력 필드 | 현재 추출 방식 | HTML/양식 의존 위험 |
| --- | --- | --- |
| `회차` | `사채의 종류`가 있는 row에서 `회차` 바로 오른쪽 셀 | `회차`가 별도 row에 있거나 오른쪽 셀이 값이 아니면 실패 |
| `종류` | 공시 제목에 `전환사채`, `교환사채`, `신주인수권부사채` 포함 여부 | 제목에 약어 또는 다른 표현만 있으면 실패 |
| `기업명(행사대상)` | `교환대상` 또는 `전환에 따라`/`전환으로 발행할`/`인수권행사에 따라`와 `종류`가 있는 row의 마지막 값 | 대상 주식 문구가 다른 라벨이면 실패 |
| `발행금액` | `사채의 권면` row의 오른쪽 끝에서 첫 숫자 | row 끝에 다른 숫자가 있으면 오추출 |
| `행사가액` | `전환가액`/`교환가액`/`행사가액` 및 `원`이 있는 row의 마지막 숫자 | 단위가 없거나 숫자가 여러 개면 오추출 |
| `납입일` | 번호 제거 후 label이 정확히 `납입일`인 row의 마지막 값 | `납입기일`, `청약/납입일` 등 변형에 약함 |
| `만기일` | `사채만기일` row의 마지막 값 | 라벨 변형에 약함 |
| `행사시작일` | `전환청구기간`/`교환청구기간`/`권리행사기간` row에서 `시작일` 기준 마지막 값 | 시작/종료가 같은 row 구조가 아니면 실패 |
| `행사종료일` | 위와 동일하게 `종료일` 기준 | 같은 위험 |
| `투자자` | 정정 아닌 table 중 첫 row에 `발행 대상자명`, `발행권면`이 있는 table을 찾고 각 row의 첫 값과 마지막 숫자를 사용 | header 문구 변경, 금액 column이 마지막 숫자가 아닌 경우 위험 |

### 사채발행파싱의 핵심 리스크

- 메인 table 선택이 고정 라벨 3개에 강하게 의존한다.
- 대부분의 값 추출이 "라벨 포함 row의 마지막 값" 또는 "마지막 숫자"에 의존한다.
- `투자자`는 별도 table header 문구에 의존한다.
- 같은 라벨이 여러 곳에 있으면 첫 번째 matching row/table이 잘못 선택될 수 있다.

## 2. 유무상증자파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/rights_issuance/__init__.py`
- `src/finiq/market_desk/web/html_parsers/rights_issuance/utils.py`
- `src/finiq/market_desk/web/html_parsers/rights_issuance/extractor.py`

### 처리 개요

유무상증자파싱도 공통 table/span 처리 결과를 사용한다.
다만 사채발행처럼 메인 table 하나만 쓰는 방식이 아니라, 정정표가 아닌 모든 table의 `logical_rows`를 합쳐서 필드를 찾는다.

### 증자 유형 분류

증자 유형은 공시 제목만 사용해 분류한다. table 내부 라벨 조합으로 유상/무상 여부를 추론하지 않는다.

| 제목 포함 문구 | 분류 |
| --- | --- |
| `유무상증자` | `mixed` |
| `무상증자` | `bonus` |
| `유상증자` | `paid` |
| 없음 | `unknown` |

제목에서 유형을 확인하지 못하면 warning을 남긴다.

의존 가정:

- 유무상증자 결정 공시는 제목에 위 문구 중 하나를 포함한다.

틀릴 수 있는 경우:

- 제목이 비어 있거나 다른 표현을 쓰는 경우
- 본문 table은 유무상증자 양식이지만 제목 메타데이터가 누락된 경우

### 필드별 추출 규칙

| 출력 필드 | 현재 추출 방식 | HTML/양식 의존 위험 |
| --- | --- | --- |
| `신주의 종류와 수` | `신주의 종류와 수` + `보통주식`/`기타주식` row의 마지막 숫자 | 주식 종류 라벨이 다르면 실패 |
| `발행목적` | `자금조달의 목적` + 고정 목적 라벨 row의 마지막 숫자 | 목적 라벨 추가/변경 시 누락 |
| `발행가액` | `신주 발행가액` + `보통주식`/`기타주식` row의 마지막 숫자 | 표 구조가 다르면 실패 |
| `기준주가` | `기준주가` + `보통주식`/`기타주식` row의 마지막 숫자 | 같은 위험 |
| `증자방식` | `증자방식` 포함 row의 마지막 값 | row 끝에 비고가 있으면 오추출 |
| `납입일` | label이 정확히 `납입일`인 row의 마지막 값 | 라벨 변형에 약함 |
| `신주권교부예정일` | 해당 문자열 포함 row의 마지막 값 | 문구 차이에 약함 |
| `상장예정일` | `신주의 상장 예정일` 포함 row의 마지막 값 | 공백/표현 차이에 약함 |
| `발행대상자` | table 첫 row에 `제3자배정 대상자`, `배정주식수`가 있어야 하며, `배정주식수` column 또는 row 마지막 숫자 사용 | header 문구/column 위치 변경에 취약 |
| `발행대상자세부엔티티` | table 첫 row에 `명칭`, `대표이사`, `최대주주`가 있어야 함 | header가 2줄이거나 문구가 다르면 실패 |

### 유무상증자파싱의 핵심 리스크

- 여러 table row를 합쳐 검색하므로 같은 라벨이 여러 table에 있으면 잘못된 row가 선택될 수 있다.
- `보통주식`, `기타주식`처럼 고정 stock label에 의존한다.
- 제3자배정 대상자와 상세 엔티티는 header row 문구에 강하게 의존한다.
- 본문 fallback은 로컬 저장 구조에 의존한다.

## 3. 주주총회파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/shareholder_meeting/__init__.py`
- `src/finiq/data_scraper/parse/domain/shareholder_meeting.py`
- `src/finiq/data_scraper/parse/table_dict.py`

### 처리 개요

주주총회파싱은 웹 parser에서 공통 `build_base_record()`를 호출해 `raw_tables`를 만들지만, 상세 필드 추출은 `extract_shareholder_meeting_details()`에 위임한다.

중요한 차이:

- 사채발행/유무상증자처럼 공통 `logical_rows`를 직접 검색하지 않는다.
- BeautifulSoup로 HTML을 다시 파싱한다.
- 안건은 `<td>` 순서에 의존한다.
- 선임/사업목적 변경 세부내역은 `<span>` section title과 그 다음 `<table>`에 의존한다.

### 안건 추출

`extract_shareholder_meeting_details()`는 모든 `<td>`를 순회한다.
각 td의 text에 아래 문구가 있으면 그 바로 다음 td를 값 cell로 본다.

| 구분 | 라벨 조건 |
| --- | --- |
| 결과 공시 | `1. 결의사항` |
| 소집/공고 | `3. 의안 주요내용` 또는 `결의사항` |

그 다음 td의 text를 줄 단위로 나눈 뒤 `_clean_agenda_text()`가 안건 marker를 기준으로 항목을 만든다.

안건 marker 예:

- `제1호`
- `제 1 호`
- `안건`
- `-제1`
- `가.`
- `나.`
- `[`
- `<`

틀릴 수 있는 경우:

- 라벨 td와 값 td가 바로 이웃하지 않는 경우
- 값이 같은 td 안에 들어 있는 경우
- 안건 번호 형식이 regex와 다른 경우
- 줄바꿈이 의미 있게 보존되지 않는 경우

### 선임 세부내역 추출

`_section_table()`은 모든 `<span>`을 순회하면서 span text가 정확히 section title과 같은지 본다.
찾으면 그 span 뒤의 첫 번째 `<table>`을 해당 section table로 사용한다.

대상 section:

| section title | 출력 분류 |
| --- | --- |
| `이사선임 세부내역` | `director` |
| `사외이사선임 세부내역` | `outside_director` |
| `감사선임 세부내역` | `auditor` |

각 table은 `parse_table_to_dicts()`로 dict row로 변환된다.
첫 row를 header로 쓰고, 중복 header는 `_1`, `_2` suffix를 붙인다.

사용하는 주요 header:

- `성명`
- `출생년월`
- `임기`
- `신규선임여부`
- `상근여부`
- `주요경력(현직포함)`
- `이사 등으로 재직 중인 다른 법인명(직위)`

틀릴 수 있는 경우:

- section title이 `<span>`이 아닌 다른 tag에 있는 경우
- section title 문구가 조금 다른 경우
- section title과 table 사이에 다른 table이 먼저 있는 경우
- header가 2단 구조라 첫 row만으로 key가 부족한 경우
- `성명` header가 다르게 표현되는 경우

### 사업목적 변경 추출

`사업목적 변경 세부내역` span 다음 table을 찾아 dict row로 변환한다.

사용하는 header:

- `구분`
- `내용`
- `내용_1`
- `이유`

특히 `내용_1`은 duplicate header 처리 결과에 의존한다.
즉 원본 table에 `내용` header가 두 번 나와야 두 번째가 `내용_1`이 된다.

틀릴 수 있는 경우:

- duplicate header 처리 결과가 예상과 다른 경우
- `변경전`, `변경후`가 별도 header로 나오는 경우
- section title 문구나 tag 구조가 다른 경우

### 주주총회파싱의 핵심 리스크

- 공통 `logical_rows` 기반이 아니라 BeautifulSoup 기반 별도 규칙이다.
- 안건은 `<td>` 순서에 매우 강하게 의존한다.
- 세부내역은 `<span>` 제목과 "그 다음 table" 구조에 의존한다.
- table header 첫 row를 key로 쓰므로 다단 header에 취약하다.

## 4. 유무형자산거래파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/asset_transaction/__init__.py`
- `src/finiq/market_desk/web/html_parsers/asset_transaction/extractor.py`
- `src/finiq/market_desk/web/html_parsers/asset_transaction/models.py`

현재 상태:

- `build_base_record()`로 공통 metadata, `raw_tables`, `raw_rows`는 생성한다.
- `AssetTransactionExtractor`는 `raw_tables`만 보관하고 실제 추출 메서드는 없다.
- `AssetTransactionRecord().to_dict()`는 빈 dict를 반환한다.

따라서 현재 HTML 구조에 의존하는 상세 필드 추출은 없다.
다만 공통 table/span 처리 결과는 record에 포함된다.

## 5. 발행증권거래파싱

관련 파일:

- `src/finiq/market_desk/web/html_parsers/security_transaction/__init__.py`
- `src/finiq/market_desk/web/html_parsers/security_transaction/extractor.py`
- `src/finiq/market_desk/web/html_parsers/security_transaction/models.py`

현재 상태:

- `build_base_record()`로 공통 metadata, `raw_tables`, `raw_rows`는 생성한다.
- `SecurityTransactionExtractor`는 `raw_tables`만 보관하고 실제 추출 메서드는 없다.
- `SecurityTransactionRecord().to_dict()`는 빈 dict를 반환한다.

따라서 현재 HTML 구조에 의존하는 상세 필드 추출은 없다.
다만 공통 table/span 처리 결과는 record에 포함된다.

## 결론

질문에 대한 답은 다음과 같다.

모든 보고서가 같은 방식은 아니다.

공통으로는 대부분 `table 수집 -> rowspan/colspan 해제 -> logical row 압축 -> 정정표 제외 -> row 검색` 기반을 공유한다.
하지만 상세 추출은 모드별로 다르다.

- 사채발행은 메인 사채 table 하나를 고른 뒤 그 안에서 row 라벨을 찾는다.
- 유무상증자는 정정 아닌 모든 table row를 합쳐서 라벨을 찾는다.
- 주주총회는 공통 logical row가 아니라 BeautifulSoup 기반으로 td 순서와 span section title을 직접 따른다.
- 유무형자산거래와 발행증권거래는 아직 상세 필드 추출이 구현되어 있지 않다.
