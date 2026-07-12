# Completed Changes Requiring Follow-up

## 2026-07-12 — 작업공간 위험 경로 검증을 실행 시점으로 지연

### Purpose

- 작업공간 경로를 텍스트로 수정하는 도중에는 중간 문자열에 대한 `high-risk data_root`
  오류를 표시하지 않는다.
- 위험 경로 차단 자체는 유지하고 실제 공시 작업 실행 시 사용자에게 오류로 표시한다.

### Implementation summary

- `/api/settings`에서 `output_root` 또는 파서 모드를 저장할 때 작업공간 폴더와 manifest를
  즉시 만들던 동작을 제거했다. 설정 저장은 표준 7단계 경로 계산과 설정 반영만 수행한다.
- 공시 자동화 프로필 정규화에서 작업공간 루트를 검증해 실행 시작 API가 고위험 루트를
  백그라운드 작업 생성 전에 400 오류로 반환하도록 했다.
- 설정 저장 시 고위험 루트를 임시 입력할 수 있고, 작업공간이 생성되지 않으며, 실제 실행
  시작 시에는 같은 루트가 거부되는 회귀 테스트를 추가했다.

### Verification

- 작업공간 및 공시 자동화 집중 Python 테스트 41건이 통과했다.
- 변경 Python 파일 compile 검사와 `git diff --check`가 통과했다.
- 실제 `resources/` 파일은 읽거나 변경하지 않았다.

## 2026-07-12 — 공시 상세 페이지 작업공간 연동과 별도 출력 설정

### Purpose

- 공시 7단계 상세 페이지가 작업별 입력 디렉토리를 따로 저장하지 않고 하나의
  `작업공간 디렉토리`를 공유하게 한다.
- 우측 설정에 `저장 디렉토리 별도 설정하기`를 기본 Off로 두고, Off일 때 결과 데이터
  경로 입력을 숨기며 표준 7단계 경로를 자동 사용한다.

### Implementation summary

- 공시내역 다운로드·변환·필터링, 공시원문 외부 저장·내부 저장·목차 분리·변환의 주 경로
  입력을 모두 공용 `output_root`에 연결했다. 루트를 바꾸면 현재 페이지와 다음 단계가 같은
  작업공간 설정을 즉시 사용한다.
- 공용 boolean 설정 `disclosure_separate_output_directory`를 추가해 모든 상세 페이지 우측
  설정 패널이 같은 값을 공유한다. 기본값은 `false`이며 실제 앱 설정도 Off로 복원했다.
- Off에서는 결과 경로 입력을 렌더링하지 않고 backend에 빈 단계 경로를 전달해
  `01-list`~`07-converted/<mode>` 표준 경로를 계산한다.
- On에서는 현재 단계의 결과 경로만 표시하고 직접 수정할 수 있다. 다운로드 출력은 변환
  입력으로, SQLite 출력은 필터 입력으로, 필터 JSON은 외부 HTML 입력으로 이어지는 방식으로
  이전 단계의 별도 출력 설정을 다음 단계에 자동 전달한다.
- 필터가 별도 JSON 경로에 실제로 저장한 파일명과 외부 HTML 압축의 별도 JSON 경로도 다음
  단계 설정에 반영해 폴더 설정과 실제 생성 파일이 어긋나지 않게 했다.
- 새 UI 용어를 `docs/ui-terminology.md`에 등록하고 모든 상세 페이지에서 같은 문구를 사용했다.

### Verification

- 경로·설정 집중 Python 테스트 54건과 관련 공시 Python 테스트 100건이 통과했다.
- 전체 frontend 테스트 90건과 MarketDesk TypeScript 검사가 통과했다.
- MarketDesk production build가 22개 route 정적 생성까지 통과했다.
- Python 전체 소스 컴파일과 `git diff --check`가 통과했다.
- 실제 로컬 브라우저에서 공시내역 변환 페이지의 Off 상태에 출력 경로가 없고, 우측 설정에서
  On으로 바꾸면 SQLite 출력 경로가 나타나며 다시 Off로 바꾸면 숨겨지는 것을 확인했다.
- 공시원문 변환 페이지로 이동해도 동일 작업공간과 Off 상태가 유지됐고 browser console
  오류가 없었다. 검증 후 실제 설정 파일의 값은 `false`로 복원했다.

## 2026-07-12 — 선택 작업공간 기준 공시 7단계 기본 경로

### Purpose

- `resources/`를 고정값으로 쓰지 않고 사용자가 선택한 `output_root`를 공시 작업공간의
  유일한 기준으로 사용한다. 선택값이 `database/`여도 같은 7단계 하위 구조를 사용한다.
- 자동화 화면뿐 아니라 다운로드·변환·필터·원문 저장·목차 분리·파싱 상세 화면에서도
  표준 단계 경로를 기본값으로 제공하면서 사용자가 직접 경로를 수정할 수 있게 한다.

### Implementation summary

- 작업공간 루트를 새로 선택하면 `01-list`부터 `07-converted/<mode>`까지의 표준 단계
  경로와 폴더를 계산한다. 이후 상세 화면에서 사용자가 수정한 개별 단계 경로는 설정과
  실제 요청에서 그대로 유지한다.
- `공시내역 다운로드` 상세 화면은 `resources/` 또는 `database/` 같은 작업공간 루트만
  입력받는다. 화면 내부의 검사·다운로드 실행 경로는 자동으로 `<루트>/01-list`를 사용한다.
- 모든 상세 화면의 경로 입력 잠금을 제거해 Finder 선택뿐 아니라 텍스트 직접 수정도
  가능하게 했다.
- 과거 `resources/KIND` 기본 루트는 새 `resources` 루트로 마이그레이션하고, 사용자가
  선택한 `database/` 같은 별도 루트와 저장된 개별 경로는 그대로 유지한다.
- 현재 애플리케이션 설정을 `resources` 루트와 표준 단계 경로로 갱신하고
  `disclosure-workspace.json` 및 7단계 폴더를 실제로 준비했다. 기존 `resources/KIND`는
  사용자 데이터 보존을 위해 이동하거나 삭제하지 않았다.

### Verification

- `2026-01-02 ~ 2026-01-03` 실제 KIND 백그라운드 작업을 실행해 627건, 7/7페이지를
  `resources/01-list/20260102_20260103`에 저장했고 페이지 번호·행 수 무결성 검사가
  통과했다. 다운로드 실행기는 루트 입력에서 `01-list`를 자동으로 선택했고 이름 오류도
  재발하지 않았다.
- 같은 실데이터를 상세 변환 경로로 실행해 378개 회사·627개 공시를 2026년 SQLite 샤드로
  저장하고, 상세 필터 경로에서 627건 전수를 읽어 `resources/03-filter/filtered.json`에
  저장했다.
- `resources/disclosure-workspace.json`의 루트, 두 파서 모드와 7단계 경로를 실제 폴더
  구조와 대조했다.
- `database/` 같은 사용자 지정 루트, 루트 변경 시 표준 경로 계산, 개별 단계 경로의 직접
  수정·저장·실행 유지, 다운로드 루트에서 `01-list` 자동 탐색을 backend/frontend 회귀
  테스트로 확인했다.
- 경로 집중 Python 테스트 53건, 전체 frontend 테스트 90건과 MarketDesk TypeScript 검사가
  통과했다. 관련 Python 묶음은 537건 중 536건이 통과했고, 남은 1건은 이번 변경과 무관한
  목차 결과 UI의 제거된 `maxSectionPatternCount`를 아직 요구하는 기존 테스트 불일치다.
- Python 전체 소스 컴파일과 `git diff --check`가 통과했다.

## 2026-07-12 — 공시 1~6단계 손상 파일·인계 무결성 강화

### Purpose

- 공시내역 다운로드, 변환, 필터링과 공시원문 외부 저장, 내부 저장, 목차 분리의 실제
  단계 인계를 점검하고 손상 파일이 완료 결과나 재사용 체크포인트로 남는 경로를 막는다.
- 좁은 실제 날짜 범위에서 KIND 응답을 받아 모킹 테스트만으로 확인할 수 없는 파일 형식,
  본문 문서번호, 목차 조합과 판단 재개 동작을 검증한다.

### Implementation summary

- 다운로드 이어하기와 폴더 검사가 기존 HTML의 존재뿐 아니라 최소 HTML 무결성도 확인한다.
  손상 파일은 누락 대상으로 다시 저장하며, 검사 결과에 손상 건수를 별도로 기록한다.
- 저수준 KIND 뷰어 저장과 내부 HTML 저장도 손상된 기존 파일을 건너뛰지 않는다. 내부 저장은
  유효하지 않은 새 응답 파일을 삭제하고 실패시키며, 부모 작업의 취소 상태를 결과에 반영한다.
- 외부 HTML 압축은 입력 파일명의 접수번호와 압축 레코드 membership을 대조하고 중복·불일치
  결과를 저장 전에 거부한다. 압축 JSON은 원자적으로 저장하고 저장 후 재검사 실패도 작업
  실패로 처리한다.
- 자동화 4단계는 압축 레코드마다 선택 가능한 본문 `docNo`가 있는지 확인한다. 4·5단계
  체크포인트 재사용 시 현재 대상 membership과 HTML 무결성을 다시 검사한다.
- 자동화 6단계는 목차 없음 또는 읽기 실패 파일이 있으면 완료 체크포인트를 만들지 않는다.
  정상 완료 소유권 파일에는 5단계 출력 fingerprint를 기록해 다른 내부 HTML 결과에 목차
  결과가 잘못 재사용되지 않도록 했다. 필터 결과가 0건인 정상 빈 실행은 계속 허용한다.
- 현재 `html-section-split` 설정 store 구조에 맞게 오래된 frontend 테스트 기대값을 수정했다.

### Verification

- `2026-01-02 ~ 2026-01-03` 실제 KIND 실행에서 공시내역 627건을 다운로드하고 SQLite
  627행으로 변환했으며, 전수 필터링 결과도 627건으로 일치했다. 2026-01-03은 실제 0건이었다.
- 실제 접수번호 `20260102000780`을 선택해 외부 HTML 저장·압축·내부 HTML 저장을 수행했다.
  압축 레코드 1건과 본문 `docNo=20260102001931`을 확인했고 외부·내부 HTML 검증이 통과했다.
- 실제 내부 HTML에서 `toc_1`, `toc_2` 조합을 찾아 자동화가 `판단 필요`에서 멈췄다.
  `toc_2`만 선택해 후속 실행했을 때 1~5단계가 재사용되고 47,080바이트 목차 HTML 1건이
  저장됐으며 저장 결과에는 `toc_2`만 남았다.
- 실제 작업공간의 SQLite 매니페스트/행 수, 필터 membership, 압축 membership, 외부·내부
  HTML, 목차 결과와 1~6단계 체크포인트 유효성을 별도 대조했고 모두 일치했다.
- 관련 Python 테스트 179건, frontend 테스트 89건과 MarketDesk TypeScript 검사가
  통과했다.
- Python 전체 소스 컴파일과 `git diff --check`가 통과했다.
- 실제 검증 산출물은 `tmp/live-disclosure-20260102-20260103-audit`에 저장했으며
  `resources/`는 읽거나 변경하지 않았다.

## 2026-07-12 — KIND 다운로드 백그라운드 작업 요약 함수 연결

### Purpose

- KIND 다운로드 작업 시작 직후 `_download_payload_summary` 이름 오류로 실패하는 회귀를
  수정한다.

### Implementation summary

- 백그라운드 작업 모듈이 다운로드 실행 모듈의 `_download_payload_summary`를 명시적으로
  가져오도록 연결했다.
- 실제 다운로드 대신 실행 함수를 대체한 회귀 테스트로 작업이 payload 요약 로그를 남긴
  뒤 정상 완료되는지 확인한다.

### Verification

- 새 백그라운드 다운로드 회귀 테스트 1건이 통과했다.
- MarketDesk 웹 앱 테스트 34건이 통과해 다운로드 라우터 import와 기존 API 동작을 함께
  확인했다.

## 2026-07-12 — 공시 자동화 범위 선택 작업표 통합

### Purpose

- 작업표 위에 작업명을 중복 표시하던 가로 범위 선택 영역을 제거한다.
- 기존 연속 범위 선택 기능을 작업표 첫 열로 옮기고 설정 진입 버튼명을 `설정`으로 바꾼다.

### Implementation summary

- 작업표 첫 열에 각 작업의 16px 체크박스형 드래그 버튼을 배치하고, 선택 범위에는 체크를
  표시하고 범위 밖에는 빈 박스를 표시한다. 별도 시작·끝 아이콘 없이 pointer capture를
  사용해 행 사이를 드래그하면 끊김 없는 실행 범위가 선택되도록 했다.
- 작업명 링크를 제거하고 아래 설정 카드와 같은 14px 일반 텍스트로 낮췄다. 상세 화면은
  기존 좌측 메뉴에서 접근하며 작업표 안의 설정 진입은 우측 `설정` 버튼만 담당한다.
- 본문 셀의 세로 여백을 16px에서 8px로 줄이고 `설정` 버튼 높이도 32px로 낮춰 작업표
  각 행의 높이를 압축했다.
- 비활성 판단 설정에 사용하는 `DisclosureLockedSettingsCard`의 최소 높이를 56px에서
  약 7/12 수준인 32px로 줄였다. 활성 설정 카드의 높이와 내용은 변경하지 않았다.
- 작업명 상세 화면 링크와 범위 선택의 키보드 조작을 유지하고, 실행 중 또는 판단 대기
  상태에서는 범위 선택을 잠근다.
- 별도 `DisclosureWorkflowRangeSelector`를 제거하고 우측 outline action과 접근성 헤더를
  모두 `설정`으로 변경했다. 같은 내용을 UI 용어집과 집중 테스트에 반영했다.

### Verification

- MarketDesk TypeScript 검사가 통과했다.
- 공시 자동화 집중 frontend test 6건이 통과했다. 16px 체크박스, 선택 범위 체크 표시,
  8px 셀 세로 여백, 작업명 링크 제거, 14px 글자 크기와 32px 잠긴 설정 카드도 회귀
  조건으로 확인한다.
- 전체 frontend test는 89건 중 88건이 통과했다. 남은 1건은 기존
  `html-section-split` settings store 구조분해 기대값 불일치다.
- 실제 브라우저의 라이트·다크 모드에서 상단 선택 영역 제거와 첫 열 손잡이 배치를
  확인했다. 2번째 작업부터 5번째 작업까지 드래그했을 때 네 행만 연속 선택됐고 browser
  console 오류는 없었다.
- 실제 `resources/` 파일은 읽거나 변경하지 않았다.

## 2026-07-12 — 공시 자동화 작업표 밀도 정렬

### Purpose

- `바로가기`를 작업명 옆이 아닌 각 row의 최우측 action 위치에 둔다.
- 작업표의 여백, 표 frame, 글자 크기를 기존 FINIQ workflow card와 맞춘다.

### Implementation summary

- 작업표에 공용 `CardContent` 여백과 둥근 border table frame을 적용하고, range box 높이와
  글자 크기 및 row cell padding을 늘렸다.
- 작업명은 16px, range와 상태 정보는 14px로 조정하고 작은 uppercase table header를
  일반 14px header로 교체했다.
- 헤더가 보이지 않는 최우측 action cell을 추가하고 `바로가기`를 1px outline button으로
  이동했다. 범위 밖 row도 opacity로 button 경계를 흐리지 않도록 배경과 text tone만 낮췄다.

### Verification

- TypeScript 검사와 MarketDesk production build가 통과했다.
- 자동화 UI 및 navigation 집중 frontend test 10건이 통과했다.
- 실제 브라우저에서 action cell이 row의 최우측 128px에 위치하고 button border가 1px로
  표시되며, 작업명 16px·range 14px·table frame 1px가 적용된 것을 확인했다.
- 전체 frontend test는 89건 중 88건이 통과했다. 남은 1건은 기존
  `html-section-split` settings store 구조분해 기대값 불일치다.
- 실제 `resources/`는 읽거나 변경하지 않았다.

## 2026-07-12 — 백그라운드 작업 TTL과 공시 다운로드 병렬 전략

### Purpose

- 완료된 백그라운드 작업과 결과가 프로세스 메모리에 무기한 남는 문제를 해결한다.
- 공시내역 다운로드에서 여러 연도를 병렬 처리할지, 한 연도 안의 페이지를 병렬 처리할지
  우측 설정에서 선택할 수 있게 한다.
- 대량 병렬 작업이 입력 전체의 Future를 한꺼번에 생성해 메모리와 스케줄링 비용을
  증가시키지 않도록 한다.

### Implementation summary

- 공용 작업 관리자와 KIND 다운로드 전용 작업 관리자에 terminal job TTL 정리를 추가했다.
  기본값은 60분이며 `job_retention_minutes` 설정으로 저장한다. 대기·실행 중 작업은 정리하지
  않고 완료·실패·중단 작업만 만료시킨다.
- 공시내역 다운로드 우측 `다운로드 설정`에 `병렬 처리 방식`과 `작업 기록 보관 시간 (분)`을
  추가했다. 병렬 방식은 `여러 연도 병렬 처리`와 `한 연도 내 페이지 병렬 처리`를 제공한다.
- `pages` 전략은 연도 폴더를 순서대로 처리하면서 현재 연도의 결과 페이지를 설정한 워커
  수만큼 병렬 저장한다. worker별 HTTP session을 분리해 닫고, 체크포인트 갱신은 lock으로
  직렬화한다. 기존 workflow input/checkpoint JSON의 필드 구조는 변경하지 않았다.
- 공통 `bounded_as_completed` helper를 추가해 다운로드 페이지, 외부 HTML 저장, 기존 파일
  검사, 폴더 무결성 검사, 외부 HTML 압축, 파싱 미리보기와 필터 소스 읽기에서 동시에
  제출되는 작업을 워커 수의 2배로 제한했다. 결과 순서가 계약인 경로는 index로 복원한다.
- HTTP 응답은 파일 저장 직후 명시적으로 닫고, 실행 종료 시 worker session과 executor가
  남지 않도록 정리한다.
- 새 UI 용어를 `docs/ui-terminology.md`에 등록하고 설정 store/API/AppConfig를 같은 명칭과
  기본값으로 맞췄다.

### Verification

- 전체 Python test 965건과 전체 frontend test 92건이 통과했다. 기존 실패 2건은 공용
  `HtmlSectionPatternCard`로 옮긴 UI를 예전 파일에서 찾던 테스트와, 루트 변경 시 canonical
  단계 경로로 재배치하는 현재 계약을 옛 기대값으로 검사하던 테스트여서 현재 구조에 맞췄다.
- 실제 FastAPI route로 TTL을 1분으로 저장하고 공용/KIND 작업을 terminal 상태로 만든 뒤,
  만료 후 두 작업 조회가 모두 404가 되는 E2E를 통과했다. 실행 중 작업과 대량 terminal
  결과 1,000건의 정리 조건도 별도 검증했다.
- 로컬 TCP 서버와 실제 `requests.Session`으로 8개 worker, 200페이지를 5회 반복해 총
  1,000페이지를 저장했다. warm-up 이후 RSS 증가는 80 KiB, file descriptor 증가는 0,
  남은 ThreadPool worker는 0이었다. HTTP 500과 실행 중 취소 후에도 descriptor와 worker가
  남지 않았다.
- 실제 KIND에서 2026-07-10의 824건/9페이지를 `pages` 전략 4개 worker로 다운로드해
  9/9 무결성, checkpoint 마지막 페이지 9와 저장 파일 10개를 확인했다. 2025-12-31부터
  2026-01-01까지 삼성전자 필터를 `years` 전략 2개 worker로 실행해 2개 연도 범위와
  총 6페이지를 모두 완료했다.
- MarketDesk TypeScript 검사와 production build가 통과했고 22개 static/dynamic route를
  생성했다. production build를 별도 포트에서 열어 우측 병렬 전략, 기본 60분 설정과
  browser error log 0건을 확인했다.
- 변경 Python 파일의 `py_compile`과 `git diff --check`가 통과했다.
- 실제 `resources/` 파일은 읽거나 변경하지 않았다.

## 2026-07-12 — 공시 자동화 드래그 범위와 Pending 판단 UI

### Purpose

- 중복된 시작·종료 dropdown 없이 작업 박스를 직접 드래그해 연속 실행 범위를 정한다.
- 범위 밖 판단 설정은 상세 form을 렌더링하지 않고 잠긴 한 줄 카드로 표시한다.
- 원문 준비 이후 목차 조합에 사용자 판단이 필요하면 workflow를 `Pending`으로 표시하고
  기존 `후속 실행`으로 이어간다.

### Implementation summary

- 작업 범위 선택기를 pointer capture 기반의 7개 박스 drag control로 교체했다. 시작점에는
  play icon, 끝점에는 flag icon을 표시하고 범위 사이 작업은 항상 연속 선택한다.
- 검색 조건, 공시 종류, 공시 조건, 목차 조합 판단이 실행 범위 밖이면 기존 제목과 lock
  icon만 있는 비대화형 `DisclosureLockedSettingsCard`로 대체한다.
- 목차 조합 카드는 원문 준비 전 `Pending`을 표시하고, 새 조합을 받은 뒤에는 결정되지 않은
  조합과 작업표 상태를 `Pending`으로 표시한다. 기존 needs-review backend 중단점과
  `후속 실행` 계약은 유지해 worker를 점유한 채 대기하지 않는다.
- 기존 상세 화면과 공용 검색·필터·목차 component는 유지했다.

### Verification

- TypeScript 검사와 MarketDesk production build가 통과했다.
- 자동화 UI 및 navigation 집중 frontend test 9건이 통과했다.
- 실제 브라우저에서 변환부터 내부 저장까지 drag 선택 시 중간 작업이 연속 선택되고 검색
  관련 카드만 잠기는 것을 확인했다. 범위를 목차 분리까지 늘리면 `Pending`이 표시됐고
  browser console 오류는 없었다.
- 전체 frontend test는 88건 중 87건이 통과했다. 남은 1건은 기존
  `html-section-split` settings store 구조분해 기대값 불일치다.
- 실제 `resources/`는 읽거나 변경하지 않았다.
