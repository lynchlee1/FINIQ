# 06 목차 경계 계약

## 목차 경계 안전 계약

- 목차 경계를 찾거나 전체 section을 분리하기 위해 표시 문자열을 하드코딩하는 방식을 금지한다. 정확히 같은 문자열, 부분 문자열, 정규식, 공백·기호 정규화, 문서 제목 목록 비교를 모두 포함한다. 이를 목차 분리 근거로 사용하는 것은 치명적인 파싱 실패로 본다.
- `CORRECTION` class는 KIND가 만든 정정 목차의 구조 identifier다. 이 목차가 첫 구간이고 뒤에 다른 목차가 있을 때만 제거한다. 제목에 `정정`이 들어갔다는 이유로 일반 머리말이나 문서 제목을 제거하지 않는다.
- tag, DOM 계층, sibling 순서, class·id, anchor 연결은 원문 생성 형식의 구조 identifier로만 사용한다. class·id의 이름이 제목처럼 보인다는 이유로 의미를 추론하지 않고, 생성 형식과 전체 입력에서 위치·유일성을 검증한 식별자만 사용한다.
- 사업 모드별로 분기하지 않고 HTML 생성 형식의 구조로 분기한다. 검증된 구조가 아닌 입력은 문자열 규칙이나 다른 selector로 우회하지 않고 실패 처리한다.

### 검증된 구조 확장

목차와 문서 제목을 다음과 같이 구분한다.

- 원문 `body` 직계 heading에 `id="toc_N"`이 있으면 이 ID를 KIND가 제공한 목차 연결로 본다. 모든 `toc_N`은 중복 없이 DOM 순서대로 증가해야 하고, 같은 문서의 구조 heading은 빠짐없이 `toc_N`을 가져야 한다.
- `COVER-TITLE`은 표지, `PART`는 최상위 부, `SECTION-N`은 N단계 section으로 분류한다. 제목 문자열이나 로마 숫자·장절 표기는 깊이 계산에 사용하지 않는다.
- `toc_N`이 없는 구형 heading 또는 paragraph 문서는 검증된 `CORRECTION`, `PART`, `COVER-TITLE`, `SECTION-N` 구조에 문서 순서대로 내부 ID를 부여한다.
- `body > div.xforms` 주 콘텐츠의 직계 `div.xforms_title`은 목차가 아니라 단일 서식의 문서 제목이며 `is_toc=false`로 분류한다. 중첩된 `xforms_title`은 하위 서식 제목이므로 경계로 사용하지 않는다.

확정한 section container의 sibling 순서에서 내용이 있는 첫 경계 이전 preamble도 별도 비목차 section으로 분리하고, 각 경계부터 다음 경계 직전까지를 각각 section으로 삼는다. HTML recovery parser가 heading 안의 제목 요소를 다음 sibling으로 옮긴 경우에는 경계와 같은 구조 class를 가진 바로 다음 요소만 제목으로 읽는다.

## 알 수 없는 목차 구조 거부

새 구조는 실제 원문과 외부 목차 연결에서 위치·ID·유일성을 검증하고 구조 identifier와 regression test를 추가한 뒤 지원한다.
