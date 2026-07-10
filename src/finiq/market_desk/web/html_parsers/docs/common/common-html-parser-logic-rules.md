# HTML 파서 공통 로직 규칙

공통 table, base record, 저장 payload의 필드 구조는
[HTML 파서 공통 데이터 구조](./common-html-parser-data-structure.md)를 따른다.
상태, 경고, 실행 오류 처리는
[HTML 파서 공통 예외 처리 규칙](./common-html-parser-exception-handling.md)을 따른다.

### HTML 파싱 일반 규칙
1. **디코딩 방식**
- byte 입력은 `utf-8`, `cp949`, `euc-kr`, `utf-8(errors="replace")` 순서로 시도한다.
- DOM을 만들 때는 항상 `lxml.html.HTMLParser(recover=True, huge_tree=True)`를 사용한다.
  - 의도 : 과거 인코딩과 불완전한 KIND HTML을 같은 parsing 경로에서 처리한다.
2. **table 파싱 기능**
- **text 정규화**
  - cell text의 줄바꿈, tab, 연속 공백을 하나의 공백으로 합친다.
    - 의도 : HTML 내부의 공백 표현이 달라도 같은 text로 비교한다.
- **공백 제거**
  - 공백을 포함한 문자열을 비교한 다음 행과 검색어의 모든 공백을 제거한 값으로 다시 비교한다.
    - 의도 : 띄어쓰기가 달라도 정상 동작한다.
- **숫자 복구**
  - 쉼표로 묶인 숫자가 올바른 3자리 grouping이 되는 경우에만 숫자 내부의 공백을 제거한 뒤 parsing한다.
    - 의도 : `1, 000, 000`처럼 span으로 분할된 숫자를 `1000000`으로 정상 인식하면서 서로 다른 숫자를 임의로 합치지 않는다.
- **rowspan 및 colspan 처리**
  - `rowspan` 또는 `colspan` 속성이 없으면 `1`로 처리한다.
    - 의도 : span 누락 table을 일반 cell로 간주하고 계속 parsing한다.
  - `rowspan` 또는 `colspan` 속성에 잘못된 값이 있으면 조용히 보정하지 않고 실패 처리한다.
    - 의도 : 잘못된 cell 확장으로 인한 오탐을 방지한다.
  - `rowspan` 또는 `colspan`은 지정된 범위로 확장하되, 원문 cell이나 span이 없는 위치에는 빈 cell을 임의로 보충하지 않는다.
    - 의도 : 원문에 없는 cell을 생성해 table 구조가 왜곡되는 것을 방지한다.
- **독립적 처리**
  - label 검색은 빈 cell과 연속된 중복 cell을 제거한 `logical_rows`를 사용한다.
    - 의도 : span 확장으로 생긴 반복 label을 줄인다.
  - column 추출은 실제 위치와 반복 cell을 보존한 `positional_rows`를 사용한다.
    - 의도 : 반복되거나 비어 있는 실제 cell 때문에 column index가 바뀌는 문제를 방지한다.
3. **입력 HTML 범위**
- 정정공시 관련 목차는 `공시원문 목차 분리` 단계에서 제외한 뒤 parser 입력으로 저장한다.
- parser는 정정 신고 table을 별도로 판별하거나 필터링하지 않는다.
  - 의도 : **절대로** parser에 별도의 정정공시 필터링 로직을 만들지 않는다.

### 공통 row 및 숫자 규칙
1. **row의 의미**
- 이 문서에서 row는 HTML table의 가로 한 줄, cell은 그 줄을 이루는 한 칸을 뜻한다.
- 공통 row 함수는 어떤 table을 사용할지 결정하지 않는다. 개별 parser가 넘긴 row 목록 안에서만 검색한다.
  - 의도 : 공통 함수가 다른 table까지 찾아가 값을 추측하지 않게 한다.
2. **검색어 포함 판정**
- `row_contains()`는 row의 모든 cell을 한 문자열로 이어 붙인 뒤, 지정한 검색어가 모두 들어 있는지 확인한다.
- 일반 비교에서 검색어를 찾지 못하면 row와 검색어에서 space 문자를 모두 제거하고 한 번 더 비교한다.
- `row_containing()`은 조건을 만족하는 첫 번째 row를 반환하고, 찾지 못하면 빈 목록을 반환한다.
  - 의도 : `신주 배정`과 `신주배정`처럼 띄어쓰기만 다른 표현은 같은 것으로 보되, 첫 번째 일치 row라는 선택 순서는 고정한다.
3. **번호 label 정규화**
- `row_with_label()`은 각 cell 맨 앞의 `숫자.`와 뒤따르는 공백만 제거한 뒤 지정 label과 정확히 비교한다.
- 예를 들어 `1. 납입일`은 `납입일`과 같다고 보지만, `1-1. 납입일`의 `1-1.`이나 label 안의 다른 문구는 제거하지 않는다.
- 조건을 만족하는 첫 번째 row를 반환하고, 찾지 못하면 빈 목록을 반환한다.
  - 의도 : 필요한 목차 번호만 제거하고 비슷한 label을 넓게 오인하지 않는다.
4. **인접 값 추출**
- `value_after()`는 cell 값이 지정 label과 정확히 같을 때 바로 오른쪽 cell 하나만 반환한다.
- label이 없거나 오른쪽 cell이 없으면 `null`에 해당하는 `None`을 반환한다.
- `last_value()`는 선택된 row의 마지막 cell을 반환하고, 빈 row이면 `None`을 반환한다.
  - 의도 : label과 값의 위치 관계를 그대로 따르고, 다른 위치의 값을 대신 사용하지 않는다.
5. **column 위치 찾기**
- `column_index()`는 각 cell의 space 문자를 제거한 값에 지정 label이 들어 있는지 왼쪽부터 확인한다.
- 첫 번째로 일치한 column 번호를 반환하고, 찾지 못하면 `None`을 반환한다.
- 찾은 번호로 값을 읽을 때는 실제 위치를 보존한 `positional_rows`를 사용한다.
  - 의도 : header를 찾는 기준과 실제 값을 읽는 column을 같은 번호로 연결한다.
6. **정수 추출**
- `parse_int()`는 지정된 cell 안에서 처음 발견한 정수 부분 하나를 반환한다. 쉼표는 제거하고 음수 기호는 보존한다.
- `parse_ints()`는 cell 안의 모든 정수 부분을 왼쪽부터 순서대로 반환한다.
- `last_int()`는 row를 오른쪽부터 확인하여 처음 정수로 parsing되는 cell의 값을 반환한다.
- `dash_as_zero=True`이면 정리한 cell 전체가 빈 문자열 또는 `-`일 때만 0으로 처리한다.
  - 의도 : 숫자를 읽을 row와 cell, 0 처리 여부는 개별 parser가 먼저 정하고 공통 함수는 선택된 범위 안의 숫자만 변환한다.
7. **실수 추출**
- `parse_float()`는 쉼표를 제거한 cell에서 처음 발견한 정수 또는 소수를 실수로 반환한다.
- 숫자를 찾지 못하면 `None`을 반환한다.
  - 의도 : 가격처럼 소수점이 있을 수 있는 값도 별도의 위치 추측 없이 선택된 cell 안에서만 변환한다.

### 입력 파일과 parser 실행
1. **입력 파일 선택**
- 공통 workflow는 입력 디렉토리와 그 아래 폴더에서 확장자가 `.html`인 파일만 찾는다.
- 찾은 경로를 정렬한 뒤 앞에서부터 처리하며, `limit`이 있으면 정렬 후 처음 `limit`개만 사용한다.
  - 의도 : 같은 폴더와 같은 설정으로 실행하면 파일 처리 순서가 달라지지 않게 한다.
2. **parser에 전달하는 값**
- 각 HTML 파일은 byte로 읽고 parser에는 `file_path`와 함께 전달한다.
- 외부 metadata에서 title을 찾았고 parser가 `title` parameter를 받을 때만 `title`도 함께 전달한다.
  - 의도 : HTML 디코딩은 공통 parser 경로에서 처리하고 title을 받지 않는 parser의 호출 방식은 바꾸지 않는다.
3. **반환 후 처리 순서**
- parser가 반환하면 먼저 원문 분석용 내부 필드를 제거하고, 다음으로 외부 metadata를 연결한 뒤, 마지막으로 record filter를 적용한다.
- filter를 통과한 record와 그 record의 warning만 최종 payload에 포함한다.
- 여기서 filter는 정한 조건에 맞는 record만 남기는 단계이다.
  - 의도 : filter가 HTML 원문 구조가 아니라 저장될 업무 필드와 외부 metadata가 연결된 결과를 기준으로 동작하게 한다.

### 외부 metadata 연결
1. **Only SoT 적용**
- Only SoT는 해당 값을 가져오는 기준 출처를 하나로만 둔다는 뜻이다.
- 외부 파일 위치와 필드별 출처는 [외부 메타데이터 병합 규칙](../external-metadata.md)만 따른다.
- 이 문서와 개별 parser 문서에서는 같은 출처 표를 다시 정의하지 않는다.
  - 의도 : 외부 필드 계약을 한 문서에서만 변경하게 한다.
2. **metadata 연결 key**
- key는 서로 같은 HTML record와 metadata를 찾아 연결하는 찾기용 값이다.
- 입력 파일명에서 확장자를 제거하고 `_` 앞부분을 metadata 연결 key로 사용한다.
- `filtered.json`과 `compressed-external-html.json` 안의 `acpt_no`는 이 key와 같은 record를 찾는 데만 사용한다.
  - 의도 : 외부 파일의 식별자가 parser가 만든 record의 `acpt_no`를 덮어쓰지 않게 한다.
3. **title 선주입**
- signature는 함수가 받을 수 있는 입력 이름 목록이고, parameter는 그 목록에 있는 각 입력 자리를 뜻한다.
- 공통 workflow는 입력 파일의 `acpt_no`로 찾은 `title`이 있고 parser signature에 `title` parameter가 있을 때만 parsing 전에 주입한다.
- signature 확인이 실패하거나 `title` parameter가 없으면 주입하지 않는다.
- parser가 빈 `title`을 반환해도 parsing 후 metadata 보강 단계에서 다시 채우지 않는다.
  - 의도 : parser가 실제 판정에 사용한 title과 반환된 title을 일치시킨다.
4. **parser 반환 후 보강**
- 공통 workflow는 parser 실행이 끝난 뒤 `doc_no`, `상장구분`, 공시 주체 회사명, 정정공시 family를 외부 metadata에서 연결한다.
- `doc_no`는 metadata 값이 있고 parser 반환 record에 값이 없을 때만 추가한다.
- `상장구분`의 metadata 값이 `유가증권`이면 `코스피`로 바꾸어 저장한다.
- 공시 주체 회사명은 사채발행과 유무상증자 mode에서만 `corp_name`으로 저장한다.
- 공시 유형별 본문 추출 필드와 `title`은 이 단계에서 변경하지 않는다.
  - 의도 : 본문 추출 결과와 외부 metadata 필드를 서로 다른 단계에서 관리한다.
5. **정정공시 family 후보**
- `compressed-external-html.json`의 `docs[]` 중 `select_id`가 `mainDoc`이고 `doc_no`가 있는 항목만 구성원 후보로 사용한다.
- 후보가 두 개 이상일 때만 정정공시 family를 만든다.
- 각 후보의 `option_index`를 정수로 변환해 순서를 정하고, 같은 순서이면 `doc_no` 문자열 순서로 정한다.
- `option_index`가 없거나 정수로 바꿀 수 없으면 임의의 기본 순서로 대체하지 않고 metadata parsing이 실패한다.
  - 의도 : 화면에 표시된 문서 선택 순서를 확인할 수 있을 때만 정정공시 순서를 기록한다.
6. **불완전한 정정공시 family 제외**
- 구성원 하나라도 같은 `selected_main_doc_no`를 가진 외부 record를 찾지 못하면 family 전체를 만들지 않는다.
- 현재 record의 `selected_main_doc_no`가 구성원 안에 없거나 마지막 구성원의 `acpt_no`가 비어 있어 family id를 정할 수 없어도 family를 만들지 않는다.
- family를 만들지 않아도 개별 HTML parser의 본문 추출 결과는 그대로 처리한다.
  - 의도 : 불완전하거나 순서를 확인할 수 없는 정정 묶음을 추측해 저장하지 않는다.
