# 공시 관계 그래프 Reference

## 경로와 형식

- 표준 경로는 다음과 같다.

```text
<data_root>/
├── 03-filter/
│   └── <mode>/filtered.json
├── 07-converted/
│   └── <mode>/parsed-<mode>.json
└── 09-disclosure-graph/
    └── disclosure-graph.json
```

- 지원하는 `<mode>`는 `rights_issuance`, `bond_issuance`, `shareholder_meeting`이다. mode별 그래프 입력은 필터 결과와 파싱 결과 한 쌍이다.
- `disclosure-graph.json`은 `finiq_disclosure_graph_v1` 형식을 쓰는 JSON 객체다.

**`format`** — 형식: string. 내용: `finiq_disclosure_graph_v1`

**`metadata`** — 형식: object. 내용: 만든 시각, mode별 입력 경로·처리/제외 건수, 검증 집계, 전체 node·edge 수

**`nodes`** — 형식: array. 내용: `id`, `label`, `type`, `group`, `tags`, `properties`를 가진 node

**`edges`** — 형식: array. 내용: `id`, `source`, `target`, `relation`, `category`, `weight`, `directed`, `properties`를 가진 edge

- node 유형은 회사, 사람, 기관, 발행 event, 증권, 자금 사용 목적, 주주총회, 의안이다.
- edge는 회사가 발행이나 주주총회를 실행한 관계, 발행 증권과 자금 목적, 투자자가 취득한 관계, 주주총회 의안·임원 관계를 표현한다.
- edge마다 `properties.evidence`에 공시 제목, 접수번호, 공시일, 원본 경로, 추출 상세를 기록해 원문을 추적할 수 있게 한다.
