# Disclosure Graph Features

## Purpose

03단계 회사·공시 metadata와 07단계 구조화 결과를 node와 edge로 바꾸고 `/disclosure-graph`에서 생성·저장·조회한다.

## Features

### Select Graph Input Modes

#### Behavior

- 필터 결과와 parsing 결과가 모두 있는 지원 mode만 그래프 입력으로 선택한다.
- 두 결과가 모두 없는 mode는 입력에서 제외한다.

#### Defaults and Exceptions

- 지원 mode에서 두 파일 중 하나만 있으면 누락 파일을 표시하고 실패 처리한다.
- 완전한 입력 쌍이 하나도 없거나 입력 JSON을 읽을 수 없으면 실패 처리한다.

### Build and Save the Graph

#### Behavior

- `그래프 생성`은 완전한 입력 쌍이 있는 모든 mode를 node·edge 집합 하나로 합친다.
- 같은 회사명이나 투자자명은 builder의 entity resolution 규칙으로 합치고, 동명이인은 발행사마다 서로 다른 person node로 유지한다.
- 임시 파일에 전체 JSON을 쓴 뒤 최종 경로로 교체해 완료되지 않은 파일을 정상 결과로 노출하지 않는다.

#### Defaults and Exceptions

- parsing 결과에 `acpt_no`가 없거나 필터 결과에서 회사 식별값을 만들 수 없으면 해당 공시를 제외하고 나머지 입력으로 계속 만든다.
- 제외 건수와 회사 식별값 누락 건수는 graph metadata에 기록한다.
- 공시일이나 허용된 대체 날짜를 지원 형식으로 변환할 수 없으면 event 날짜를 만들지 않고 전체 그래프 생성을 실패 처리한다.
- edge 가중치가 없으면 `0.0`을 저장한다.

### Resolve Issuer Names

#### Behavior

기본 회사명이 비어 있으면 mode별 parsing 결과의 발행사, 필터 결과의 회사명, 제출인 순서로 발행사 이름을 선택한다.

### Classify Investor Nodes

#### Behavior

투자자 이름이 수집한 회사와 일치하지 않으면 이름 표기를 기준으로 Person, Company 또는 Organization node를 만든다.

### Connect Acquisition Relationships

#### Behavior

유무상증자 결과에서 증권 node를 만들 수 없으면 투자자 `ACQUIRED` edge를 발행 event에 연결한다.

### Discover Workspace Inputs

#### Behavior

- `작업공간 디렉토리`에서 mode별 03단계와 07단계 결과를 찾는다.
- 찾은 경로를 그래프 입력으로 전달하고 완전한 입력 쌍이 있는 mode만 포함한다.

#### Defaults and Exceptions

- `작업공간 디렉토리`가 없거나 실제 디렉토리가 아니면 실행 요청을 실패 처리한다.

### Load a Saved Graph

#### Behavior

- `저장 결과 불러오기`는 저장 파일 구조를 검사한 뒤 현재 조회 요청에 맞춰 화면에 전달한다.

#### Defaults and Exceptions

- 저장 파일이 없거나 JSON으로 읽을 수 없으면 실패 처리한다.
- 저장 형식과 metadata가 현재 규칙과 다르거나 node·edge 목록을 읽을 수 없으면 실패 처리한다.
- 저장 입력을 확정하지 못하면 화면 결과를 만들지 않는다.

### Explore the Graph

#### Behavior

- 화면에서 node 유형을 고르고 `노드 검색`, 확대·축소, 핀 고정, 이웃 보기, 최단 경로와 상세 보기를 실행한다.
- 저장한 node와 edge는 graph-viewer의 `Obsidian-like` 스타일로 표시한다.

#### Defaults and Exceptions

- 탐색 상태는 화면 입력이며 저장된 node와 edge를 바꾸지 않는다.

### Select Node Display Labels

#### Behavior

node 표시명은 이름, 증권 유형, 사용 유형, 발행 유형, node ID 순서로 선택한다.

#### Defaults and Exceptions

- 표시명 선택은 화면 문자열만 정하며 저장한 node 속성은 바꾸지 않는다.
