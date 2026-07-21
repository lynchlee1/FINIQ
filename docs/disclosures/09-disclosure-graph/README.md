### **1. Summary**

#### **기능 요약**

- 03단계의 회사·공시 metadata와 07단계의 구조화된 파싱 결과를 node와 edge로 변환한다.
- `/disclosure-graph`에서 그래프를 생성·저장하거나 이전 저장 결과를 다시 불러온다.
- 저장된 node와 edge는 기존 graph-viewer의 `Obsidian-like` 스타일로 표시한다.

#### **세부 설명**

- 각 공시 유형의 값 추출 규칙은 [공시원문 변환](../07-html-parse/README.md)과 연결된 mode 문서가 설명한다.
- 회사별 공시 시간선 화면은 [Graph View](../../ontology/graph-view/README.md)가 설명한다.
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

- 지원하는 `<mode>`는 `rights_issuance`, `bond_issuance`, `shareholder_meeting`이다. 한 mode는 필터 결과와 파싱 결과가 모두 있을 때만 그래프 생성 대상이 된다.
- `disclosure-graph.json`은 `finiq_disclosure_graph_v1` 형식의 JSON 객체다.

| key | 형식 | 내용 |
|---|---|---|
| `format` | string | `finiq_disclosure_graph_v1` |
| `metadata` | object | 생성 시각, mode별 입력 경로·처리/제외 건수, 검증 집계, 전체 node·edge 수 |
| `nodes` | array | `id`, `label`, `type`, `group`, `tags`, `properties`를 가진 node |
| `edges` | array | `id`, `source`, `target`, `relation`, `category`, `weight`, `directed`, `properties`를 가진 edge |

- node 유형은 회사, 사람, 기관, 발행 event, 증권, 자금 사용 목적, 주주총회와 의안이다.
- edge는 회사의 발행·주주총회 실행, 발행 증권과 자금 목적, 투자자의 취득, 주주총회 의안·임원 관계를 표현한다.
- 각 edge의 `properties.evidence`에는 원문을 추적할 수 있는 공시 제목, 접수번호, 공시일, 원본 경로와 추출 상세를 기록한다.

### **2. Core**

#### **Feature**

**[Input Handling] 그래프 입력 mode 선택 기능**

- **목적:** 그래프에 포함할 변환 유형을 완전한 입력 쌍으로 제한한다.
- 필터 결과와 파싱 결과가 모두 있는 지원 mode만 그래프 생성 대상으로 선택한다.
- 두 결과가 모두 없는 mode를 제외하는 것은 정상 입력 선택 규칙이므로 Fallback이 아니다.
<br>

**[Core Processing] 그래프 생성·저장 기능**

- **목적:** 파싱 결과를 웹 그래프가 직접 읽을 수 있는 하나의 문서로 고정한다.
- `그래프 생성`은 입력 쌍이 완전한 모든 mode를 하나의 node·edge 집합으로 합친다.
- 같은 회사와 투자자 이름은 builder의 entity resolution 규칙으로 합치고, 동명이인은 발행사 범위의 서로 다른 person node로 유지한다.
- 임시 파일에 전체 JSON을 쓴 뒤 최종 경로로 교체하므로 완료되지 않은 파일을 정상 결과로 노출하지 않는다.
<br>

**[Core Processing] 투자자 node 분류 기능**

- **목적:** 수집한 회사와 투자자 이름의 관계에 따라 node 유형을 결정한다.
- 투자자 이름이 수집한 회사와 일치하지 않으면 이름 표기를 기준으로 Person, Company 또는 Organization node를 만든다.
- 이는 정상 entity resolution 규칙이므로 Fallback이 아니다.
<br>

#### **Fallback**

**[Core Processing] 식별값 누락 공시 제외 기능**

- **목적:** node와 edge를 식별할 수 없는 공시를 제외하고 나머지 입력으로 그래프 생성을 계속한다.
- 파싱 결과에 `acpt_no`가 없거나 필터 결과에서 회사 식별값을 만들 수 없으면 해당 공시를 제외한다.
- 제외 건수와 회사 식별값 누락 건수는 graph metadata에 기록한다.
<br>

**[Core Processing] 발행사 이름 대체 기능**

- **목적:** 기본 발행사 이름이 비어 있을 때 명시된 다른 출처로 그래프 생성을 계속한다.
- 회사명이 비어 있으면 변환 유형별로 파싱 결과의 발행사, 필터 결과의 회사명·제출인 순서에서 사용 가능한 값을 선택한다.
<br>

**[Core Processing] 취득 관계 축소 연결 기능**

- **목적:** 증권 node를 만들지 못한 유무상증자 결과도 발행 event까지의 관계로 보존한다.
- 유무상증자 결과에 증권 node가 없으면 투자자의 `ACQUIRED` edge를 발행 event에 연결한다.
<br>

**[Core Processing] edge 가중치 대체 기능**

- **목적:** edge 가중치가 누락된 결과를 정의된 중립값으로 저장한다.
- edge 가중치가 없으면 `0.0`을 저장한다.
<br>

#### **Shutdown**

**[Input Handling] 입력 계약 오류시 중단하기**

- **목적:** 그래프 생성에 필요한 입력 파일 쌍과 JSON을 확정하지 못하면 Core를 실행하지 않는다.
- 지원 mode의 필터 결과와 파싱 결과 중 하나만 있으면 누락 파일을 표시하고 실패 처리한다.
- 완전한 입력 쌍이 하나도 없으면 실패 처리한다.
- 입력 JSON을 읽을 수 없으면 실패 처리한다.
<br>

**[Core Processing] event 날짜 확정 실패시 중단하기**

- **목적:** 그래프 node와 edge에 기록할 날짜를 만들 수 없으면 불완전한 결과를 저장하지 않는다.
- 공시일이나 허용된 대체 날짜를 지원 형식으로 변환할 수 없으면 실패 처리한다.
- 날짜는 그래프 결과에 들어갈 업무값이므로 날짜 확정 실패는 Core Processing이다.
<br>

### **3. Serving**

#### **Feature**

**[Input Handling] 작업공간 입력 탐색 기능**

- **목적:** 사용자가 파일을 하나씩 고르지 않아도 표준 결과를 찾는다.
- `작업공간 디렉토리`에서 변환 유형별 03·07단계 결과를 찾는다.
- 찾은 경로를 Core 입력으로 전달한다. mode 포함·제외 판정은 Core가 수행한다.
<br>

**[Input Handling] 저장 결과 조회 기능**

- **목적:** 그래프를 다시 만들지 않고 저장 결과를 불러온다.
- `저장 결과 불러오기`는 파일 구조를 검사한 뒤 화면에 전달한다.
- 저장된 Core 결과는 현재 조회 요청의 화면 결과를 만들기 위한 입력이므로 Input Handling이다.
<br>

**[Input Handling] 그래프 탐색 표시 기능**

- **목적:** 불러온 그래프를 사용자가 조건과 관계에 따라 탐색하게 한다.
- 화면에서는 node 유형 선택, `노드 검색`, 확대·축소, 핀 고정, 이웃 보기, 최단 경로와 상세 보기를 사용할 수 있다.
- 탐색 상태는 화면 입력이며 저장된 node와 edge를 바꾸지 않는다.
<br>

**[Input Handling] node 표시명 선택 기능**

- **목적:** node 유형별 표시 후보를 정해진 우선순위로 선택한다.
- node 표시명은 이름, 증권 유형, 사용 유형, 발행 유형, node ID 순서로 정한다.
- 이 선택은 화면의 표시 문자열만 정하며 저장된 node 속성을 바꾸지 않는다.
- 정상 표시 규칙에서 정한 순서대로 선택하므로 Fallback이 아니다.
<br>

#### **Fallback**

- 없음.

#### **Shutdown**

**[Input Handling] 작업공간 요청 오류시 중단하기**

- **목적:** 그래프 입력이나 저장 결과를 찾을 작업공간을 임의로 추측하지 않는다.
- `작업공간 디렉토리`가 없거나 실제 디렉토리가 아니면 실행 요청을 실패 처리한다.
<br>

**[Input Handling] 저장 결과 오류시 중단하기**

- 저장 파일이 없거나 JSON으로 읽을 수 없으면 실패 처리한다.
- 저장 형식과 metadata가 현재 규칙과 다르거나 node·edge 목록을 읽을 수 없으면 실패 처리한다.
- 아직 화면 결과를 만들기 전 저장 입력을 확정하지 못한 실패이므로 Input Handling이다.
