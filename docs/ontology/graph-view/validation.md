# Graph View 검증과 중단

아래 경로는 `src/` 기준이다.

## 그래프 입력

- **finiq/data/ontology\_query.py**
- **지정한 그래프 JSON을 읽을 수 없거나 edge에 source·target node가 없음**
  - 오류로 처리한다.

아래 경로는 `frontend/finiq_GUI/packages/graph-viewer/src/` 기준이다.

## 그래프 가져오기

- **utils/validation.ts, core/useGraphViewer.ts**
- **graph JSON에서 node·edge 구조에 validation error가 있음**
  - 초기 graph이면 빈 graph를 표시하고 사용자가 가져온 graph이면 현재 graph를 교체하지 않고 오류 목록을 반환한다.

## 관계 입력

- **components/RelationshipEdgeForm.tsx**
- **새 관계에서 weight가 비어 있거나 유한한 0 초과 100 이하 숫자가 아님**
  - 생성 버튼을 비활성화하고 API 요청을 보내지 않는다.

아래 경로는 `frontend/finiq_GUI/apps/market-desk/src/` 기준이다.

## 회사 그래프 조회

- **app/company/[id]/CompanyGraphViewer.tsx**
- **회사 그래프 조회가 실패함**
  - 오류로 처리한다.

아래 경로는 저장소 최상위 폴더 기준이다.

## Neo4j 연결

- **scripts/sync\_to\_neo4j.py**
- **Neo4j driver를 불러오지 못함**
  - 오류로 처리한다.
