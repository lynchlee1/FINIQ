# 09 파일과 저장 형식

- `<data_root>/03-filter/<mode>/filtered.json`과 `<data_root>/07-converted/<mode>/parsed-<mode>.json`을 입력으로 받아 `<data_root>/09-disclosure-graph`에 `disclosure-graph.json`을 저장한다.

## `<data_root>/03-filter/<mode>/filtered.json`

- 그래프 node에 연결할 회사·공시 metadata를 담은 입력 파일이다.

## `<data_root>/07-converted/<mode>/parsed-<mode>.json`

- node와 edge로 바꿀 mode별 구조화 공시 결과를 담은 입력 파일이다.

### 제약과 분기

- 지원하는 `<mode>`는 `rights_issuance`, `bond_issuance`, `shareholder_meeting`이다.

## `<data_root>/09-disclosure-graph/disclosure-graph.json`

- mode별 공시 결과를 node와 edge 집합 하나로 합친 출력 파일이다.
- `disclosure-graph.json`은 `finiq_disclosure_graph_v1` 형식을 쓰는 JSON 객체다.

**`format`** — 형식: string. 내용: `finiq_disclosure_graph_v1`

**`metadata`** — 형식: object. 내용: 만든 시각, mode별 입력 경로·처리/제외 건수, 검증 집계, 전체 node·edge 수

**`nodes`** — 형식: array. 내용: `id`, `label`, `type`, `group`, `tags`, `properties`를 가진 node

**`edges`** — 형식: array. 내용: `id`, `source`, `target`, `relation`, `category`, `weight`, `directed`, `properties`를 가진 edge

- node 유형은 회사, 사람, 기관, 발행 event, 증권, 자금 사용 목적, 주주총회, 의안이다.
- edge는 회사의 발행·주주총회, 발행 증권과 자금 목적, 투자자의 취득, 주주총회의 안건·후보·선임·재직·감사·거래 관계를 표현한다.
- edge마다 `properties.evidence`에 공시 제목, 접수번호, 공시일, 원본 경로, 추출 상세를 기록해 원문을 추적할 수 있게 한다.
