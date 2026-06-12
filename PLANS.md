# 문서 JSON 압축 시스템 설정 복원

## 목적
- `문서 JSON 압축` 화면도 다른 화면과 같이 우측 `시스템 설정` 버튼을 유지한다.
- 외부 HTML 압축 병렬 처리 워커 수를 해당 설정 패널에서 조정할 수 있게 한다.

## 구현 요약
- 압축 화면의 `시스템 설정` 패널을 다시 표시하고, `압축 처리` 섹션을 추가했다.
- `병렬 워커 수` 입력을 추가해 `parallel_workers` payload로 전달한다.
- 값이 비어 있으면 백엔드의 자동 워커 선택을 사용한다.

## 검증 결과
- `python3 -m pytest tests/market_desk/test_kind_web_service.py -k "compress_disclosure_external_html_payload or html_parse_modes_are_registered_documented_and_listed_in_ui"` 통과: 4 passed, 138 deselected.
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build` 통과.
- Browser 확인: `http://localhost:3002/html-download`에서 `문서 JSON 압축` 전환 후 `시스템 설정` 버튼이 보이고, 패널을 열면 `압축 처리`, `병렬 워커 수`, 자동 선택 도움말이 보임.

# 시스템 설정 명칭 통일

## 목적
- 우측 설정 패널 제목이 화면마다 `필터 설정`, `조회 설정`, `저장 설정`, `분할저장 설정`처럼 다르게 보이는 문제를 정리한다.
- 설정 패널 제목은 모두 `시스템 설정`으로 통일한다.

## 구현 요약
- `ActionDock`에 전달되는 `settingsTitle` 값을 모든 사용처에서 `시스템 설정`으로 변경했다.
- 설정 패널 본문에 남아 있던 `추가 병합 설정`, `추가 원천 데이터 설정`, `추가 시장 이력 설정` 문구를 `추가 시스템 설정`으로 정리했다.
- 페이지 제목과 상태 메시지는 설정 패널 이름이 아니므로 기존 의미를 유지했다.

## 검증 결과
- `rg -n "settingsTitle=|필터 설정|변환 설정|저장 설정|조회 설정|그래프 설정|시장 이력 설정|병합 설정|원천 데이터 설정|분할저장 설정|자산 엑셀 설정" frontend/finiq_GUI/apps/market-desk/src` 확인: `settingsTitle` 값은 모두 `시스템 설정`; 남은 `설정` 문구는 페이지 제목 또는 상태 메시지.
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build` 통과.

# 외부 HTML 문서 JSON 압축 병렬화 및 압축 설정 정리

## 목적
- `외부 HTML 문서 JSON 압축` 실행이 HTML 파일을 순차 파싱해 오래 걸리는 문제를 줄인다.
- 압축 화면의 기존 `압축 설정` 블록을 정리하고, 병렬 처리 설정은 `시스템 설정`에서 다룬다.

## 구현 요약
- 외부 HTML 압축 처리에서 파일별 compact record 생성을 `ProcessPoolExecutor`로 병렬 처리하도록 바꿨다.
- 기본 워커 수는 파일 수와 CPU 개수 중 작은 값으로 잡고, API payload의 `workers` 또는 `parallel_workers`로 명시 제어할 수 있게 했다.
- 병렬 완료 순서와 관계없이 기존 파일 정렬 순서대로 결과 JSON records를 저장하도록 유지했다.
- 압축 화면의 예전 `압축 설정`, `분할저장` 체크박스, `최대 처리 건수` 설정 블록을 제거했다. 분할저장은 본문 경로 입력 옆의 On/Off 버튼만 사용한다.
- 압축 화면의 `시스템 설정`에는 병렬 워커 수만 남겼다.

## 검증 결과
- `python3 -m pytest tests/market_desk/test_kind_web_service.py -k "compress_disclosure_external_html_payload or html_parse_modes_are_registered_documented_and_listed_in_ui"` 통과: 4 passed, 138 deselected.
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build` 통과.
- Browser 확인: `http://localhost:3002/html-download`에서 `문서 JSON 압축` 화면에는 `외부 HTML 문서 JSON 압축`, `외부 HTML 입력 경로`, `압축 JSON 저장 경로`, `시스템 설정` 버튼이 보이고, 설정 패널에는 `병렬 워커 수`가 보임.

# 문서 JSON 압축 실행 블록 분리

## 목적
- `/html-download`의 `문서 JSON 압축` 화면에서 경로 입력과 실행 버튼이 한 카드에 섞여 보이는 문제를 줄인다.
- `외부 HTML 저장` 화면처럼 입력 블록과 실행 블록을 분리해 화면 구조를 맞춘다.

## 구현 요약
- `외부 HTML 문서 JSON 압축` 카드에는 `외부 HTML 입력 경로`, `압축 JSON 저장 경로` 입력만 남겼다.
- 압축 화면 전용 `작업 실행` 카드를 추가하고, `실행`과 작업 중지 버튼을 별도 블록에 배치했다.
- 압축 화면 본문 카드의 `외부 HTML 입력 경로` 옆에 `분할저장 On/Off` 버튼을 추가했다.

## 검증 결과
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build` 통과.
- `/tmp/finiq-pytest-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k html_parse_modes_are_registered_documented_and_listed_in_ui` 통과: 1 passed, 140 deselected.

# 공시원문 외부 저장 작업 화면 분리

## 목적
- 공시원문 외부 저장 화면에서 저장, 압축, 분할저장 구조 전환이 같은 중요도로 섞여 보이는 문제를 줄인다.
- 같은 `/html-download` URL 안에서 상단 작업 전환으로 `외부 HTML 저장`과 `문서 JSON 압축` 화면을 분리한다.
- `저장 설정`은 개별 카드로 흩뜨리지 않고 기존 우측 설정 패널 구조를 유지한다.
- 일반적인 분할저장 구조 전환은 공시원문 저장 전용 화면에서 빼고 외부 데이터 변환 페이지로 이동한다.

## 구현 요약
- `공시원문 외부 저장` 화면 상단에 `외부 HTML 저장`/`문서 JSON 압축` 전환 버튼을 추가했다.
- 압축 화면에서는 저장용 `필터 결과 JSON 파일`과 `저장 경로`를 숨기고, 별도 `외부 HTML 입력 경로`와 `압축 JSON 저장 경로`만 받도록 분리했다.
- 압축의 `분할저장`과 `최대 처리 건수` 옵션은 우측 `저장 설정` 패널의 `압축 설정`으로 유지했다.
- `공시원문 외부 저장` 화면에서 `분할저장 구조 전환` 카드와 관련 검증/manifest 보정 로직을 제거했다.
- `/utility` 페이지 제목을 `외부 데이터 변환` 성격에 맞게 정리하고, 분할저장 구조 전환 실행 payload가 복사가 되도록 `move: false`를 명시했다.
- 새 압축 경로 설정을 저장하기 위해 `html_external_compress_input_directory`, `html_external_compress_output_directory` 설정 키를 추가했다.

## 검증 결과
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build` 통과.
- `/tmp/finiq-pytest-venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "html_parse_modes_are_registered_documented_and_listed_in_ui or download_disclosure_html_contents_payload"` 통과: 9 passed, 132 deselected.
- `python3 -m pytest tests/market_desk/test_partition_utility.py` 통과: 7 passed.
- `npm --prefix frontend/finiq_GUI/apps/market-desk run dev` 실행: `http://localhost:3000`에서 기동.
- Browser 확인: `/html-download` 기본 화면에는 `외부 HTML 저장`/`문서 JSON 압축` 전환 버튼과 외부 저장 입력이 보이고, `분할저장 구조 전환` 카드는 보이지 않음.
- Browser 확인: `/html-download`의 `문서 JSON 압축` 화면에는 `외부 HTML 입력 경로`, `압축 JSON 저장 경로`가 보이고 저장용 `필터 결과 JSON 파일`/`작업 실행` 카드는 숨겨짐.
- Browser 확인: 압축 화면에서 우측 `저장 설정` 패널을 열면 `압축 설정`, `분할저장`, `최대 처리 건수`가 보임.
- Browser 확인: `/utility`에는 `분할저장 구조 전환` 페이지가 보임.

# 설정 API 500 오류 수정

## 목적
- `fetchSettings`가 `/api/config` 호출 중 `HTTP 500`으로 실패하는 문제를 확인하고, 프론트엔드 설정 저장소와 백엔드 설정 API의 키 불일치를 정리한다.
- `/html-download` 화면에서 사용하는 압축/병합 경로 설정이 저장 후 다시 불러와지도록 한다.

## 구현 요약
- `AppConfig`와 저장 설정 키 목록에 `html_merge_output_path`, `html_content_compressed_json_path`, `html_external_compress_input_directory`, `html_external_compress_output_directory`를 추가했다.
- `/api/settings` 요청 모델과 `/api/config` 응답 payload가 같은 네 설정 키를 받거나 반환하도록 맞췄다.
- 네 설정 키가 POST 후 GET에서도 유지되는 회귀 테스트를 추가했다.

## 검증 결과
- `pytest -q tests/market_desk/test_server.py tests/test_persistence_api.py` 통과: 3 passed.
- `PYTHONPATH=src python3 -m uvicorn finiq.market_desk.web.app:app --host 127.0.0.1 --port 8765`로 백엔드 기동 확인.
- `curl http://127.0.0.1:8765/api/config` 응답 `200 OK`.
- `curl http://127.0.0.1:3000/api/config` 응답 `200 OK`.
