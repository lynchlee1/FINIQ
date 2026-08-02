# Graph View

> **문서 목적:** 회사별 공시 시간선으로 구성하는 Graph View 화면의 Feature, Fallback과 Shutdown을 설명한다.
>
> **다루지 않는 내용:** 03·07단계 결과를 표준 graph JSON으로 생성·저장하는 기능은 [09 공시 관계 그래프](../../disclosures/09-disclosure-graph/README.md), 주가-공시 차트는 [Chart View](../chart-view/README.md), Triple Barrier는 [공시 분석](../disclosure-analysis/README.md)에서 설명한다.

## Feature

아래 경로는 `src/finiq/` 기준이다.

### `ontology-query`

- `ACQUIRED` edge가 `collapse_minor_threshold`를 넘으면 가중치가 큰 3개를 남기고 나머지를 합계 node와 edge로 묶는다.
- Neo4j 동기화는 node의 `riskLevel`과 `riskDescription`이 `null`이면 임의의 위험도나 설명을 만들지 않고 `null`을 전달한다.

아래 경로는 `frontend/finiq_GUI/` 기준이다.

### `graph-viewer`

**그래프 데이터 표시·내보내기 기능**

- 회사 공시 시간선 node 그래프는 서버가 반환한 `timeline` 순서를 유지하며 앞의 80개 공시만 사용한다.
- 그래프 JSON 내보내기는 node와 edge의 교환용 주요 값만 저장한다.
- KO 위험도 다시 계산은 수동 기본값이 아닌 node를 대상으로 최대 3번 전파하고 현재 그래프 상태에 반영한다.

**그래프 배치·pin 상태 기능**

- 그래프 배치는 화면에 보이는 node 위치만 저장하고, 다시 읽을 때 저장된 위치가 있는 node만 고정한다.
- 기본 pin 한도는 3개다. node를 누르거나 옮겨 한도를 넘으면 가장 오래전에 pin한 node부터 자동으로 해제하며, 이후 graph·layout JSON을 내보내면 현재 pin 상태가 저장된다.

## Fallback

아래 경로는 `src/` 기준이다.

- **finiq/api/server.py**
- **그래프 조회 record에 node `label`·`type` 또는 edge `relation`·`category`·`weight`·`directed`가 없음**
  - node label은 node ID, type은 `Company`를 사용한다. edge relation은 `related`, category는 `other`, weight는 0, directed는 `true`를 사용한다.
  - key가 있지만 값이 `null`이거나 빈 문자열이면 기본값으로 바꾸지 않는다.
- **Cypher 조회 node에 `id` property가 없거나 새 edge의 Neo4j 관계 type이 빈 문자열임**
  - node ID는 Neo4j element ID, 관계 type은 `RELATED_TO`를 사용한다.

아래 경로는 저장소 최상위 폴더 기준이다.

- **scripts/sync\_to\_neo4j.py**
- **APOC를 사용할 수 없음**
  - 단순 property `SET`을 사용하고 edge는 `CONNECTED_TO` 관계로 저장한다. 원래 relation은 property에 남긴다.

- **finiq/data/ontology_query.py**
- **회사나 투자자 시작 node를 첫 key로 찾지 못함**
  - 회사는 정규화한 종목 코드와 원래 입력을 차례로 찾는다. 투자자 이름이 투자자 index에 없으면 같은 이름의 회사를 찾는다.

아래 경로는 `frontend/finiq_GUI/packages/graph-viewer/src/` 기준이다.

- **utils/validation.ts**
- **가져온 node의 label·type이 비었거나 `tags`·`properties` 형식이 잘못됨**
  - label은 node ID, type은 `default`를 사용하고, tags는 문자열만 남기며 properties는 빈 객체로 바꾼다.
- **가져온 edge의 ID·category·weight·directed·properties가 생략되거나 category·properties 형식이 맞지 않거나 relation이 빈 문자열임**
  - ID는 배열 위치로 만들고 빈 relation은 `related`, category는 `other`, weight는 1, directed는 `false`, properties는 빈 객체를 사용한다. 유효한 양수가 아닌 weight는 오류로 처리한다.

- **core/useGraphViewer.ts**
- **초기 graph JSON을 전달하지 않음**
  - 내장 예시 graph를 표시한다.
- **요청한 테마 preset이 없음**
  - 현재 테마에 지정된 preset, `Default`, `AI Studio`, 코드 기본 모양 순서로 사용 가능한 설정을 선택한다. preset을 삭제하면 현재 테마의 preset이나 남은 첫 preset을 선택한다.

- **utils/export.ts**
- **SVG에 넣을 node의 좌표나 edge의 양 끝 node가 없음**
  - 좌표가 있는 node와 양 끝 node 및 좌표를 모두 찾은 edge만 SVG에 넣는다. 좌표가 있는 node가 없으면 다운로드를 시작하지 않는다.
- **PNG용 canvas image를 만들지 못함**
  - 다운로드를 시작하지 않는다.

- **components/RMAPView.tsx, components/SPLCView.tsx, components/KOGridView.tsx**
- **분석 기준 node ID가 없거나 일치하는 node가 없음**
  - 입력 node 배열의 첫 node를 기준으로 사용한다.
- **분석 대상 edge의 양 끝 node를 찾지 못함**
  - RMAP은 해당 관계를 제외하고 equity 관계를 최대 3단계까지 탐색한다. SPLC도 해당 관계를 제외하며 KO 위험 전파는 찾지 못한 상대 node를 건너뛴다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **app/company/[id]/page.tsx**
- **회사 화면 응답에 직접 지정된 종목 코드가 없음**
  - 회사 ID에서 추론한 종목 코드를 사용한다.
- **`default_visible`인 차트 그룹이 없음**
  - 응답의 모든 차트 그룹을 펼친 상태로 시작한다.

- **app/graph/OntologyNodeGraph.tsx**
- **공시 시간선 항목에 `acpt_no`나 제목이 없음**
  - 공시 시각과 배열 index로 event node ID를 만들고, 제목은 `acpt_no` 또는 `공시`를 사용한다.

## Shutdown

아래 경로는 `src/` 기준이다.

- **finiq/data/ontology\_query.py**
- **지정한 그래프 JSON을 읽을 수 없거나 edge의 source·target node가 없음**
  - 오류로 처리한다.

아래 경로는 `frontend/finiq_GUI/packages/graph-viewer/src/` 기준이다.

- **utils/validation.ts, core/useGraphViewer.ts**
- **graph JSON의 node·edge 구조에 validation error가 있음**
  - 초기 graph이면 빈 graph를 표시하고, 사용자가 가져온 graph이면 현재 graph를 교체하지 않고 오류 목록을 반환한다.
- **components/RelationshipEdgeForm.tsx**
- **새 관계의 weight가 비어 있거나 유한한 0 초과 100 이하 숫자가 아님**
  - 생성 버튼을 비활성화하고 API 요청을 보내지 않는다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

- **app/company/[id]/CompanyGraphViewer.tsx**
- **회사 그래프 조회가 실패함**
  - 오류로 처리한다.

아래 경로는 저장소 최상위 폴더 기준이다.

- **scripts/sync\_to\_neo4j.py**
- **Neo4j driver를 불러오지 못함**
  - 오류로 처리한다.
