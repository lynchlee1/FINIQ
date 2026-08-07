# Annual SQLite Conversion Features

## Purpose

HTML로 저장한 KIND 조건검색 결과를 검색 가능한 연도별 SQLite 조각으로 바꾼다.

## Features

### Parse the KIND Result Table

#### Behavior

01단계 HTML에서 공시 결과표를 읽어 SQLite에 저장할 공시 행을 만든다.

#### Defaults and Exceptions

- 원본 페이지가 없거나 파일을 읽을 수 없으면 변환을 중단한다.
- 페이지 번호가 중복되거나 이어지지 않으면 변환을 중단한다.
- 페이지별 pagination이 서로 다르면 변환을 중단한다.
- 입력 페이지를 확정할 때 앞선 페이지 값, 다수결이나 복구 overlay로 입력을 추정하지 않는다.
- 파일명에서 페이지 번호를 확정할 수 없으면 변환과 원본 직접 조회를 중단한다.
- 결과표 범위, 회사·공시 식별값 또는 이미지 `alt`를 확정할 수 없으면 변환을 중단한다.
- 원본 `.body`는 한 번만 읽으며 다른 표나 필드로 대신하지 않는다.
- `classification_path`, 구형 JSON classification이나 이름순 파일 탐색을 사용하면 변환을 중단한다.

### Deduplicate Disclosures

#### Behavior

같은 `acpt_no`를 가진 행을 같은 공시로 처리해 중복 없이 SQLite에 저장한다.

#### Defaults and Exceptions

- 모든 원본 `tbody > tr`을 순서대로 확인한다.
- 처음 읽은 행만 SQLite에 저장한다.
- 뒤에 나온 행은 중복 행 수에 포함한다.

### Extract Company Display Metadata

#### Behavior

회사 칸에서 시장과 badge를 읽어 공시 행의 표시 정보로 저장한다.

#### Defaults and Exceptions

- 이미지가 있으면 첫 번째 이미지의 `alt`를 시장으로, 나머지 이미지의 `alt`를 badge로 저장한다.
- 이미지가 없으면 시장은 `null`, badge는 빈 목록으로 저장한다.

### Build Annual SQLite Shards

#### Behavior

공시일에서 연도를 읽어 연도별 SQLite 조각을 만든다.

#### Defaults and Exceptions

- 공시일이 네 자리 연도로 시작하지 않으면 해당 조각을 저장하지 않고 변환을 중단한다.
- SQLite FTS5 표를 만들 수 없으면 해당 조각을 저장하지 않고 변환을 중단한다.

### Record Conversion Provenance

#### Behavior

SQLite 조각마다 원본과 변환 결과를 manifest에 기록한다.

### Validate Result Integrity

#### Behavior

입력 행이 저장이나 중복 집계에서 빠지지 않았는지 다음 식으로 검증한다.

- 페이지별 `원본 행 수 = 저장 행 수 + 중복 행 수`
- 전체 `원본 행 수 = 실제 SQLite 행 수 + 중복 행 수`
- 연도별 실제 SQLite 행 수 = manifest의 연도별 저장 행 수
- 연도별 저장 행 수 합계 = manifest의 전체 저장 행 수

#### Defaults and Exceptions

- 페이지별, 연도별 또는 전체 행 수가 manifest와 실제 SQLite에서 일치하지 않으면 결과를 사용하지 않고 변환을 중단한다.
