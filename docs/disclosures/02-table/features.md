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
- 기간 폴더별 pagination의 전체 공시 건수와 모든 BODY에서 실제로 읽은 공시 행 수가 다르면 변환과 기존 데이터 검토를 중단한다.
- 입력 페이지를 확정할 때 앞선 페이지 값, 다수결이나 복구 overlay로 입력을 추정하지 않는다.
- 파일명에서 페이지 번호를 확정할 수 없으면 변환과 원본 직접 조회를 중단한다.
- 결과표 범위, 공시 식별값, 존재하는 회사 링크의 식별값 또는 이미지 `alt`를 확정할 수 없으면 변환을 중단한다.
- 회사 링크가 없는 행은 공시 자체가 유효하면 회사 관계가 없는 정상 공시로 저장한다. 회사명·제출인이나 회사 칸 문구로 회사 식별값을 대신 만들지 않는다.
- 회사 링크가 둘 이상이면 한 회사를 확정할 수 없으므로 변환을 중단한다.
- 원본 `.body`는 한 번만 읽으며 다른 표나 필드로 대신하지 않는다.
- `classification_path`, 구형 JSON classification이나 이름순 파일 탐색을 사용하면 변환을 중단한다.
- 원본 BODY 페이지는 `table_workers` 범위에서 병렬 파싱하고, 중복 제거와 SQLite 저장은 원본 페이지·행 순서로 적용한다.
- 병렬 파싱 결과는 최대 `table_workers * 2`개 페이지씩 입력 순서로 소비하며 전체 페이지의 원시 행 목록을 한꺼번에 보관하지 않는다.
- 변환과 `기존 데이터 검토`는 실행마다 입력 경로를 한 번 열거해 원본 폴더, BODY 경로와 페이지 번호를 확정하고 같은 실행의 검증·파싱·집계에서 공유한다.
- 원본 목록은 실행 사이에 저장하거나 재사용하지 않으며, 실행할 때마다 현재 입력 경로에서 다시 만든다.

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

- 회사 링크가 있으면 `company_id`와 회사 링크의 `title`을 회사 관계로 저장하고 `company_key`는 `company_id`와 같게 둔다.
- 회사 링크가 없으면 `company_key`, `company_name`, `company_id`를 `null`로 저장한다.
- 회사 칸의 표시 문자열은 회사 관계와 분리해 `company_cell_text`에 저장한다.

#### Defaults and Exceptions

- 이미지가 있으면 첫 번째 이미지의 `alt`를 시장으로, 나머지 이미지의 `alt`를 badge로 저장한다.
- 이미지가 없으면 시장은 `null`, badge는 빈 목록으로 저장한다.

### Build Annual SQLite Shards

#### Behavior

입력 경로 아래의 모든 기간별 결과 폴더를 읽고, 각 공시의 공시일에서 연도를 읽어 연도별 SQLite 조각을 만든다.

- 원본 폴더의 시작일·종료일이나 폴더 개수는 SQLite 조각의 경계가 아니다.
- 같은 연도의 여러 기간 폴더에서 읽은 공시는 모두 해당 연도의 `<YEAR>.sqlite` 하나에 저장한다.
- 같은 `acpt_no`가 여러 기간 폴더에 있으면 전체 입력에서 처음 읽은 행만 저장하고 나머지는 중복 행으로 집계한다.
- 기존 SQLite에 새 기간만 추가하지 않는다. 실행할 때마다 현재 입력 경로의 모든 원본으로 연도별 임시 SQLite를 완성한 뒤 기존 연도 파일을 교체한다.
- 모든 연도별 임시 SQLite와 manifest가 완성된 뒤 하나의 세대로 게시한다. 게시 중 오류가 나면 기존 조각과 manifest를 모두 복원하며, 애플리케이션의 manifest 독자는 세대 게시가 끝날 때까지 같은 잠금에서 기다려 서로 다른 세대를 섞어 읽지 않는다.

#### Defaults and Exceptions

- 공시일이 네 자리 연도로 시작하지 않으면 해당 조각을 저장하지 않고 변환을 중단한다.
- SQLite FTS5 표를 만들 수 없으면 해당 조각을 저장하지 않고 변환을 중단한다.
- 여러 기간을 한 연도 SQLite에 포함하려면 SQLite 생성 입력을 개별 기간 폴더가 아니라 그 폴더들의 공통 상위 경로로 지정하고, 포함할 원본 폴더를 모두 유지해야 한다.
- 개별 기간 폴더만 입력하면 그 폴더에서 읽은 행만으로 연도 SQLite를 다시 만든다. 다른 기간의 기존 SQLite 행을 자동으로 이어 붙이지 않는다.

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
- 회사 관계가 없는 저장 행 수 = manifest의 `unlinked_disclosures`
- `기존 데이터 검토`는 다운로드한 원본 페이지를 다시 집계하고 변환 기록의 페이지·전체·연도별 건수와 실제 연도별 SQLite 파일의 행 수를 모두 비교한다.

#### Defaults and Exceptions

- 페이지별, 연도별 또는 전체 행 수가 manifest와 실제 SQLite에서 일치하지 않으면 결과를 사용하지 않고 변환을 중단한다.
- 원본 pagination의 전체 공시 건수와 원본 BODY의 실제 공시 행 수가 다르면 SQLite를 만들기 전에 중단한다.
- manifest를 다시 확인할 때 SQLite 조각의 실제 행 수 검증은 설정된 worker 수 안에서 조각별로 병렬 실행한다.
