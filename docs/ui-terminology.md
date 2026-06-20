# UI Terminology

UI 문구를 추가하거나 바꿀 때는 이 파일의 용어를 먼저 따른다. 새 버튼명이나 기능명을 즉석에서 만들지 않는다.

## General Rules

- 기존 화면, 라우트, 백엔드 로그, 테스트에서 쓰는 용어를 우선한다.
- 같은 기능은 페이지, 버튼, 카드 제목, 상태 문구에서 같은 명칭을 쓴다.
- 새 기능명이 필요하면 구현 전에 이 파일에 용어를 추가하고, 같은 변경에서 UI와 테스트를 맞춘다.
- 파일 형식 설명은 도움말이나 상세 문구에만 넣고, 버튼명에는 넣지 않는다.

## Disclosure HTML Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Viewer HTML save workflow | 공시원문 외부 저장 | Navigation/page workflow name. |
| Content HTML save workflow | 공시원문 내부 저장 | Navigation/page workflow name. |
| Content HTML section workflow | 공시원문 목차 분리 | Navigation/page workflow name. |
| Content HTML section scan action | 목차 스캔 | Button/action that scans per-document TOC lists in a folder. |
| Content HTML section save action | 목차 저장 | Button/action that splits each HTML file into TOC-specific output folders. |
| Content HTML document TOC table | 문서별 목차 | Table listing per-file section lists. |
| Content HTML problem file table | 문제 파일 | Table listing files without TOC sections and files that failed to read. |
| Content HTML problem file setting | 문제 파일 표시 수 | Setting for the maximum combined problem-file rows returned by scan. |
| Content HTML scan summary row | 스캔 결과 | Row box showing folder scan counts. |
| Content HTML job status row | 작업 상태 | Row box showing the latest job/API status log. |
| Viewer HTML save mode/button | 외부 HTML 저장 | Top mode button in 공시원문 외부 저장. |
| Viewer HTML compression mode/button | 외부 HTML 압축 | Use for the compact JSON creation from saved viewer HTML. |
| Content HTML save mode/button | 내부 HTML 저장 | Top mode button in 공시원문 내부 저장. |
| Content HTML merge mode/button | 내부 HTML 병합 | Use for merging saved content HTML into JSON. |
| Source folder input mode | 폴더 입력 | Toggle label. |
| Source JSON file input mode | JSON 파일 입력 | Toggle label. |
| Output split storage | 분할저장 | Keep this spelling. |
| Align with existing metadata | 기존 메타데이터 기준으로 설정 맞추기 | Button label. |

## Utility Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Utility sidebar group | 유틸리티 | Use for the sidebar group containing `분할저장`. |
| Partition storage conversion workflow | 분할저장 구조 전환 | Use for the Utility page/card that converts between flat folders and year-split folders. |
| Price data top-level workflow | 주가데이터 | Use as the top-level menu for Quantiwise-based price data pages. Do not repeat it in page titles. |
| Quantiwise sidebar group | Quantiwise | Use as the left sidebar group under the `주가데이터` top-level workflow. |
| Price data Excel preview sidebar item | Excel 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel`. |
| Price data convert sidebar item | Parquet 변환하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/convert`. |
| Price data Parquet preview sidebar item | Parquet 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/parquet`. |
| Price data merge sidebar item | Parquet 병합하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/merge`. |
| Price data Excel preview workflow | Excel 미리보기 | Use for the `/utility/assets-excel` navigation label and page title. |
| Price data Excel convert workflow | Parquet 변환하기 | Use for the `/utility/assets-excel/convert` navigation label and page title. |
| Price data Parquet preview workflow | Parquet 미리보기 | Use for the `/utility/assets-excel/parquet` navigation label and page title. |
| Price data Parquet merge workflow | Parquet 병합하기 | Use for the `/utility/assets-excel/merge` navigation label and page title. |
| Output or saved data path | 데이터 경로 | Use instead of `저장 경로` or `저장 폴더` for reusable path inputs. |
| Source data path | 입력 데이터 경로 | Use for folder/file path inputs that feed a workflow. Add the source type in parentheses only when needed, e.g. `(Raw JSON)`. |
| Result data path | 결과 데이터 경로 | Use for folder/file path inputs that receive workflow output when the page also has an input path. Add the output type in parentheses only when needed, e.g. `(SQLite)`. |
| Quantiwise Parquet grouped result table | Parquet 모아보기 | Use for the table that lists generated Parquet outputs on `Parquet 미리보기`. |
| Quantiwise merge candidate table | 병합대상 모아보기 | Use for the selectable merge-candidate table on `Parquet 병합하기`. |
| Quantiwise merge target path | 병합 대상 데이터 경로 | Use for the single input path on `Parquet 병합하기`. |
| Quantiwise merge output path | 병합 결과 데이터 경로 | Use for the path where `Parquet 병합하기` writes the merged Parquet result. |
| Quantiwise same-folder merge setting | 동일 폴더에서 작업하기 | System setting for forcing merge output work into `병합 대상 데이터 경로`. |
| Quantiwise cleanup merged items setting | 병합된 요소 정리하기 | System setting for moving successfully merged input Parquet files into `merged`. |
| Quantiwise duplicate recursive scan setting | 내부까지 검사 | System setting for including subfolders recursively in `중복 검사하기`; default is off. |
| Quantiwise duplicate Parquet cleanup action | 중복 검사하기 | Button/action on `Parquet 병합하기` that finds same-account Parquet files fully covered by a more complete same-account file before deletion. |
| Quantiwise conversion pre-run check | 변환 전 확인 | Use for the automatic check that scans Excel files without saving before `Quantiwise 변환`. |
| Quantiwise conversion target Excel table | 대상 파일 | Use for the selectable Excel file table on `Parquet 변환하기`. |
| Quantiwise account ID mapping | 계정-ID 매핑 | Use for the editable Sheet/account_id/account_name mapping in `Parquet 변환하기`. |
| Quantiwise failed-only resume button | 실패분 이어서 실행 | Use for rerunning `Parquet 변환하기` while skipping Sheet Parquet outputs already completed in the data path. |

## Ontology Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Ontology real-data workspace | Graph View | Use for the production Ontology analysis page. |
| Ontology chart workspace | Chart View | Use for the production Ontology event-price chart page. |
| Ontology data status | 데이터 상태 | Source readiness panel for KIND and Quantiwise data. |
| Ontology company selector | 회사 선택 | Company selector backed by KIND SQLite shards, shown in the right settings panel. |
| Ontology stock selector | 종목 선택 | Top selector for changing the active stock in `A000000` format. |
| Ontology node graph | 공시 관계 그래프 | Obsidian-like graph-viewer canvas showing company, disclosure group, and disclosure event relationships. |
| Ontology node search | 노드 검색 | Search input for nodes inside the Ontology node graph. |
| Ontology graph unpin action | 핀 해제 | Clears pinned nodes in the Ontology node graph. |
| Ontology event-price chart | 주가-공시 차트 | Plot combining Quantiwise price candles and KIND disclosure markers. |
| Ontology chart condition panel | 공시 조건 | Top condition box on Chart View that manages company search, `resources/KIND` disclosure category selection, and chart display buttons. |
| Ontology chart company section | 회사명 | Section label for company-name search in the Chart View condition panel. |
| Ontology chart disclosure section | 공시내역 | Section label for KIND disclosure category selection in the Chart View condition panel. |
| Ontology chart disclosure group selector | 공시 선택 | Selector label for choosing `전체` or one category folder under `resources/KIND`. |
| Ontology event timeline | 공시 타임라인 | List of visible disclosures for the selected company and period. |
| Ontology disclosure analysis | 공시 분석 | Event analysis workspace for triple-barrier and related disclosure tests. |
| Ontology triple barrier execution action | Triple Barrier 실행 | Button/action on `공시 분석` that calculates and stores Triple Barrier labels. |
| Ontology triple barrier event basis | 이벤트 기준일 | Selector for using disclosure date or disclosure timestamp as event time. |
| Ontology triple barrier price basis | 가격 기준 | Selector for close-based or intraday high/low-based barrier checks. |
| Ontology triple barrier result table | 결과 테이블 | Stored Triple Barrier label result table on `공시 분석`. |
| Ontology chart frequency selector | 일봉/5일봉/20일봉/월봉 | Chart candle aggregation selector below the chart action buttons. |
| Ontology chart type selector | 캔들/종가선 | Chart type selector for OHLC candles or close-only line plotting. |
| Ontology final report marker | 최종보고서 | Y/N field for whether a disclosure is the latest report in a correction chain. |
| Ontology full date range | 전체 기간 | Default date range for Graph View chart and disclosure analysis. |
| Ontology chart fullscreen action | 전체화면 | Opens the chart in an app-level fullscreen overlay. |
| Ontology chart exit fullscreen action | 전체화면 닫기 | Closes the chart fullscreen overlay. |
| Ontology chart zoom sensitivity | 확대/축소 민감도 | Chart interaction setting in the right settings panel. |
| Ontology chart marker placement setting | 공시 마커 위치 | Settings control for where disclosure markers render on the price chart. |
| Ontology chart marker shape setting | 공시 마커 모양 | Settings control for disclosure marker symbol shape on the price chart. |

## Right Dock Panels

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Activity panel | 실행 현황 | Use for the right dock activity button and panel title across pages. |
| Notification panel | 알림 | Use only for errors, warnings, confirmations, or user action required. |
| Settings panel | 설정 | Use as the generic right dock settings title unless a page-specific settings title is already established. |
