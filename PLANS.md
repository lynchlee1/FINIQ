## 공시원문 외부/내부 저장 페이지 기능 점검

목적:
- `공시원문 외부 저장`, `공시원문 내부 저장` 페이지의 기능 의미가 아니라 오작동 가능성을 중심으로 점검한다.
- 내부 계산 단계는 인터넷 요청이 아니므로 rate limit 대상에서 제외된다는 전제를 UI와 검증 기록에 반영한다.
- 내부 저장의 원본 분할저장 설정 누락을 더 구체적으로 안내하고, route 단위 회귀 테스트를 추가한다.

점검 결과:
- 치명적/즉시 중단급 오류는 확인하지 못했다. 프론트는 `HtmlDownloadPageView`를 `external`/`content` variant로 분기하고, 각 variant의 source payload key와 시작/취소/검사 endpoint가 백엔드 라우트와 대체로 일치한다.
- 외부 저장은 `source_json_path` 또는 JSON payload에서 접수번호를 수집하고, `output_split_by_year`에 따라 저장/검사/이어하기 대상 경로를 동일한 규칙으로 계산한다.
- 내부 저장은 외부 저장 폴더의 viewer HTML 또는 `compressed-external-html.json`에서 `doc_no`를 찾아 본문 HTML을 저장하며, `source_split_by_year`와 `output_split_by_year`를 분리해서 처리하는 백엔드 테스트가 존재한다.
- 폴더 검사/삭제는 외부/내부 저장이 같은 `clean_disclosure_html_output_directory_payload`를 공유한다. 이 자체는 큰 문제는 아니지만, 내부 저장 route 단위 테스트가 부족해 source/output 분할 옵션이 프론트 payload에서 백엔드까지 그대로 전달되는지 회귀 방지가 약하다.
- `최대 요청/분`은 KIND에 인터넷 요청을 보내는 저장 단계에만 적용되는 것이 맞다. 외부 HTML JSON 압축, 내부 HTML JSON 병합처럼 이미 저장된 로컬 파일을 읽어 계산하는 단계는 rate limit 대상이 아니며, 현재 프론트 payload도 해당 작업에는 `max_requests_per_minute`를 보내지 않는다.

개선 사항:
- 내부 저장 페이지의 `폴더 검사하기` route 테스트를 추가했다. `/api/disclosures/html/content-download/inspect-folder`에 `source_directory`, `source_split_by_year`, `output_split_by_year`를 함께 보냈을 때 `source_type=content`, 요청 접수번호, 삭제 후보 산정이 기대대로 나오는지 확인한다.
- 외부 HTML JSON 압축과 내부 HTML JSON 병합 버튼은 저장 실행과 별도 작업이지만 같은 `최대 처리 건수(limit)` 입력을 공유한다. 사용자가 운영 옵션으로 오해하지 않도록 `테스트 옵션`으로 분리했다.
- `최대 요청/분` 문구가 압축/병합 같은 내부 계산에도 적용되는 것처럼 보이지 않게 필드 도움말과 압축/병합 카드 설명을 추가했다.
- 분할저장 옵션은 내부 저장에서 원본 폴더 분할 여부와 출력 폴더 분할 여부가 별도 토글이다. 원본 폴더가 연도별인데 `공시원문 외부 저장 경로` 옆 분할저장을 끄면 대상 HTML을 찾지 못하므로, source split 설정 불일치 가능성을 안내하는 오류 메시지와 테스트를 추가했다.
- 외부 저장 폴더에 압축 JSON을 같은 위치에 쓰는 흐름은 허용 보조 파일 목록에 포함되어 있어 기본 검사와 충돌하지 않는다. 다만 연도별 압축 JSON은 split 검사일 때만 허용되므로, split 모드가 맞지 않으면 검사/삭제 후보로 잡힐 수 있다. 이 동작을 의도한 정책으로 유지할지, 압축 JSON은 split 설정과 무관하게 보존할지 결정이 필요하다.

작성한 코드:
- `frontend/finiq_GUI/apps/market-desk/src/app/html-download/_components/HtmlDownloadPageView.tsx`
  - `최대 요청/분`에 "KIND에 인터넷 요청을 보내는 저장 실행에만 적용"된다는 help 문구를 추가했다.
  - `최대 처리 건수`를 `테스트 옵션`으로 분리하고 테스트 실행 또는 샘플 JSON 생성 때만 입력하도록 help 문구를 조정했다.
  - 외부 HTML JSON 압축, 내부 HTML JSON 병합 카드 설명에 로컬 파일 처리라 `최대 요청/분`이 적용되지 않는다고 명시했다.
- `src/finiq/market_desk/web/disclosure_html.py`
  - 내부 저장 원본 폴더에 연도별 하위 폴더가 있는데 `source_split_by_year`가 꺼져 대상 HTML을 찾지 못하는 경우, `source_split_by_year` 활성화를 안내하는 오류 메시지를 반환한다.
- `tests/market_desk/test_kind_web_app.py`
  - 내부 저장 `inspect-folder` route가 source/output 분할 옵션을 유지하고 삭제 후보를 산정하는지 검증하는 테스트를 추가했다.
- `tests/market_desk/test_kind_web_service.py`
  - 연도별 원본 폴더에서 `source_split_by_year` 누락 시 구체적 오류 메시지가 나오는지 검증하는 테스트를 추가했다.

검증:
- `pytest tests/market_desk/test_kind_web_app.py::test_html_content_download_inspect_folder_route_honors_split_options tests/market_desk/test_kind_web_service.py::test_download_disclosure_html_contents_payload_explains_missing_source_split`
  - 통과.
- `pytest tests/market_desk/test_kind_web_service.py -k "download_disclosure_html_contents_payload or clean_disclosure_html_output_directory"`
  - 14개 통과.
- `pytest tests/market_desk/test_kind_web_app.py -k "html_download_inspect_folder or html_content_download_inspect_folder"`
  - 4개 통과.
- `npm run build --workspace @finiq/app-market-desk`
  - `frontend` 디렉토리에서 실행, 통과.

## 공시내역 필터링 결과 영역 정리

목적:
- 공시내역 필터링 페이지의 결과 영역에서 실제 확인에 필요 없는 요약 정보 박스와 JSON 원문 미리보기를 제거한다.
- 필터 결과 테이블과 페이지 이동 기능은 유지해 화면을 더 단순하게 만든다.

작성한 코드:
- `frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx`
  - `필터 결과` 카드 아래의 요약 정보 박스 렌더링을 삭제했다.
  - 요약 정보 박스 전용 계산값인 `companyCount`를 삭제했다.
  - 하단 JSON 미리보기 `<pre>` 렌더링을 삭제했다.
  - JSON 미리보기 전용 `jsonPreview` 계산을 삭제했다.

검증:
- `npm run build --workspace @finiq/app-market-desk`
  - 통과.
