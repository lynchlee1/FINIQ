# 공시 관계 그래프 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 자료 흐름

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

- 지원하는 `<mode>`는 `rights_issuance`, `bond_issuance`, `shareholder_meeting`이다. 한 mode는 필터 결과와 파싱 결과가 모두 있을 때만 그래프로 만든다.
- `disclosure-graph.json`은 `finiq_disclosure_graph_v1` 형식을 쓰는 JSON 객체다.

**`format`** — 형식: string. 내용: `finiq_disclosure_graph_v1`

**`metadata`** — 형식: object. 내용: 만든 시각, mode별 입력 경로·처리/제외 건수, 검증 집계, 전체 node·edge 수

**`nodes`** — 형식: array. 내용: `id`, `label`, `type`, `group`, `tags`, `properties`를 가진 node

**`edges`** — 형식: array. 내용: `id`, `source`, `target`, `relation`, `category`, `weight`, `directed`, `properties`를 가진 edge

- node 유형은 회사, 사람, 기관, 발행 event, 증권, 자금 사용 목적, 주주총회, 의안이다.
- edge는 회사가 발행이나 주주총회를 실행한 관계, 발행 증권과 자금 목적, 투자자가 취득한 관계, 주주총회 의안·임원 관계를 표현한다.
- edge마다 `properties.evidence`에 공시 제목, 접수번호, 공시일, 원본 경로, 추출 상세를 기록해 원문을 추적할 수 있게 한다.

## 처리 계약

### 정상 동작

#### 그래프 입력 mode 선택

그래프에 포함할 변환 유형을 완전한 입력 쌍으로 제한한다.
- 필터 결과와 파싱 결과가 모두 있는 지원 mode만 그래프 입력으로 고른다.
- 두 결과가 모두 없는 mode는 입력에서 제외한다.

#### 그래프 만들기·저장

파싱 결과를 웹 그래프가 직접 읽을 수 있는 문서 한 파일로 고정한다.
- `그래프 생성`은 입력 쌍이 완전한 모든 mode를 node·edge 집합 하나로 합친다.
- 같은 회사명이나 투자자명은 builder에 정한 entity resolution 규칙으로 합친다. 동명이인은 발행사마다 서로 다른 person node로 유지한다.
- 임시 파일에 전체 JSON을 쓴 뒤 최종 경로로 교체하므로 완료되지 않은 파일을 정상 결과로 노출하지 않는다.

#### 투자자 node 분류

수집한 이름이 회사와 투자자 목록에 어떻게 나타나는지에 따라 node 유형을 정한다.
- 투자자 이름이 수집한 회사와 일치하지 않으면 이름 표기를 기준으로 Person, Company 또는 Organization node를 만든다.

## 화면과 서비스 계약

### 정상 동작

#### 작업공간 입력 탐색

사용자가 파일을 하나씩 고르지 않아도 표준 결과를 찾는다.
- `작업공간 디렉토리`에서 변환 유형별 03·07단계 결과를 찾는다.
- 찾은 경로를 그래프 입력으로 전달하고 완전한 입력 쌍이 있는 mode만 포함한다.

#### 저장 결과 조회

그래프를 다시 만들지 않고 저장 결과를 불러온다.
- `저장 결과 불러오기`는 파일 구조를 검사한 뒤 화면에 전달한다.
- 저장한 그래프를 현재 조회 요청에 맞춰 화면에 표시한다.

#### 그래프 탐색 표시

불러온 그래프를 사용자가 조건과 관계에 따라 탐색하게 한다.
- 화면에서 node 유형을 고르고 `노드 검색`, 확대·축소, 핀 고정, 이웃 보기, 최단 경로, 상세 보기를 실행한다.
- 탐색 상태는 화면 입력이며 저장된 node와 edge를 바꾸지 않는다.

#### node 표시명 선택

node 유형별 표시 후보를 정해진 우선순위로 선택한다.
- node 표시명은 이름, 증권 유형, 사용 유형, 발행 유형, node ID 순서로 정한다.
- 이 선택은 화면에 보일 문자열만 정하며 저장한 node 속성은 바꾸지 않는다.
- 정한 순서에 따라 표시 이름을 고른다.
