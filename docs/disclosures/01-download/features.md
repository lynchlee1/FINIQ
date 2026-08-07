# KIND Search Result Download Features

## Purpose

KIND 공시 조건검색 결과를 페이지별로 내려받아 이후 단계에서 사용할 수 있게 저장한다.

## Features

### Download KIND Search Results

#### Behavior

공시 자동화 01단계에서 정한 검색 조건으로 KIND 공시 목록을 페이지별로 내려받는다.

#### Defaults and Exceptions

- 검색 조건을 검증할 수 없거나 저장된 조건을 현재 형식으로 정확히 바꿀 수 없으면 검색 범위를 바꾸지 않고 실패 처리한다.

### Validate Existing Data Integrity

#### Behavior

연도별 저장 결과가 현재 KIND 검색 결과와 맞아 재사용할 수 있는지 확인한다.

- 본문 파일이 있는 폴더에는 읽을 수 있고 필수 필드와 현재 `format`을 갖춘 `kind_workflow.input.json`이 있어야 한다.
- `kind_workflow.input.json`의 조건으로 연도별 재검색한 전체 공시 수는 저장값과 같아야 한다.
- 페이지 번호는 중복 없이 1부터 연속해야 한다.
- 본문 간 전체 페이지 수와 건수는 일치해야 한다.

#### Defaults and Exceptions

- 기존 결과 폴더를 읽을 수 없으면 실패 처리하고 빈 결과로 취급하지 않는다.
- 메타데이터 내 조건으로 KIND에 요청을 보냈을 때 전체 페이지 수나 건수를 조회하지 못하면 실패 처리한다.
- 무결성 검증이 실패한 기간의 본문과 workflow 보조 파일은 현재 실행 입력에서 제외한다.

### Record Download Metadata and Resume

#### Behavior

다운로드 조건, 페이지별 진행 내역과 검증 상태를 metadata로 남긴다.

#### Defaults and Exceptions

- 다운로드가 정상 완료되지 않으면 `kind_workflow.input.json`을 만들지 않는다.
- 중단된 다운로드를 재개하면 `kind_workflow.checkpoint.json`에 저장된 마지막 페이지와 pagination 정보를 재개 기준으로 사용한다.
- 저장된 pagination을 읽을 수 없으면 앞선 페이지 값이나 `null` 요약으로 대신하지 않는다.

### Verify Download List Consistency

#### Behavior

한 기간의 모든 페이지를 받은 직후 같은 검색 조건으로 첫 페이지를 다시 요청한다.

#### Defaults and Exceptions

- 다시 받은 페이지 정보와 공시 행이 첫 다운로드와 같을 때만 새 임시 결과를 게시한다.
- 두 목록이 다르면 실패 처리하고 새 임시 결과를 게시하지 않으며 이전 기간 결과를 유지한다.

### Display Results and Progress

#### Behavior

누락 페이지와 다운로드 진행 내역을 화면에 전달한다.

#### Defaults and Exceptions

- 전체 누락 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.
- 직접 실행의 진행 내역은 실행 중에만 전달한다.
- 백그라운드 작업은 정해진 줄 수만큼 최근 진행 내역을 보관한다.

### Redownload Entire Date Range

#### Behavior

기존 결과 검증이 실패하면 기존 결과 삭제와 전체 기간 재다운로드 여부를 사용자가 결정하게 한다.

1. 공시 자동화 화면 오른쪽 `알림`에서 어느 기간의 결과가 어떤 검사에서 어긋났는지 확인한다.
2. 기존 결과를 지우고 해당 기간을 처음부터 다시 받아도 되는지 판단한다.
3. 다시 받으려면 `전체 다시 받기`를 누른다. 기존 결과를 유지하려면 누르지 않는다.
4. 작업이 끝나면 01단계 상태가 `완료`로 바뀌었는지 확인한다.

#### Defaults and Exceptions

- 서버는 `workflow_status=needs_download_confirmation`과 함께 충돌 내역과 `download_confirmation`을 반환한다.
- `download_confirmation`은 현재 01단계 설정과 충돌별 기간·종류·저장 페이지 수·현재 KIND 페이지 수로 만든 hash다.
- 다시 실행할 때 서버가 반환한 `download_confirmation`을 보내야 기존 결과를 지우고 빈 시작 상태에서 전체 검색기간의 페이지를 다시 만든다.
- 그사이 01단계 설정이나 충돌 내역이 바뀌면 새 확인값을 반환하고 다시 판단을 기다린다.
- 사용자가 허가하지 않으면 기존 결과를 지우거나 다시 받지 않는다.
