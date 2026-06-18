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
| Quantiwise sidebar group | Quantiwise | Use as a peer sidebar group to `유틸리티`. |
| Quantiwise Excel preview sidebar item | Excel 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel`. |
| Quantiwise convert sidebar item | Parquet 변환하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/convert`. |
| Quantiwise Parquet preview sidebar item | Parquet 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/parquet`. |
| Quantiwise merge sidebar item | 병합하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/merge`. |
| Quantiwise Excel preview workflow | Quantiwise - Excel 미리보기 | Use for the `/utility/assets-excel` navigation label and page title. |
| Quantiwise Excel convert workflow | Quantiwise - Parquet 변환하기 | Use for the `/utility/assets-excel/convert` navigation label and page title. |
| Quantiwise Parquet preview workflow | Quantiwise - Parquet 미리보기 | Use for the `/utility/assets-excel/parquet` navigation label and page title. |
| Quantiwise Parquet merge workflow | Quantiwise - 병합하기 | Use for the `/utility/assets-excel/merge` navigation label and page title. |
| Output or saved data path | 데이터 경로 | Use instead of `저장 경로` or `저장 폴더` for reusable path inputs. |
| Quantiwise Parquet grouped result table | Parquet 모아보기 | Use for the table that lists generated Parquet outputs on `Quantiwise - Parquet 미리보기`. |
| Quantiwise merge candidate table | 병합대상 모아보기 | Use for the selectable merge-candidate table on `Quantiwise - 병합하기`. |
| Quantiwise merge target path | 병합 대상 경로 | Use for the single input path on `Quantiwise - 병합하기`. |
| Quantiwise merge output path | 병합 결과 경로 | Use for the path where `Quantiwise - 병합하기` writes the merged Parquet result. |
| Quantiwise same-folder merge setting | 동일 폴더에서 작업하기 | System setting for forcing merge output work into `병합 대상 경로`. |
| Quantiwise cleanup merged items setting | 병합된 요소 정리하기 | System setting for moving successfully merged input Parquet files into `merged`. |
| Quantiwise duplicate recursive scan setting | 내부까지 검사 | System setting for including subfolders recursively in `중복 검사하기`; default is off. |
| Quantiwise duplicate Parquet cleanup action | 중복 검사하기 | Button/action on `Quantiwise - 병합하기` that finds same-account Parquet files fully covered by a more complete same-account file before deletion. |
| Quantiwise conversion pre-run check | 변환 전 확인 | Use for the automatic check that scans Excel files without saving before `Quantiwise 변환`. |
| Quantiwise account ID mapping | 계정-ID 매핑 | Use for the editable Sheet/account_id/account_name mapping in `Parquet 변환하기`. |
| Quantiwise failed-only resume button | 실패분 이어서 실행 | Use for rerunning `Parquet 변환하기` while skipping Sheet Parquet outputs already completed in the data path. |

## Ontology Workflow

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Quant platform feature workspace | Quant Platform Workspace | Use on the Ontology page for the professional quant feature surface. |
| Canonical research data feature | Research Data Store | Feature name for versioned datasets, lineage, and quality checks. |
| Factor research feature | Factor & Signal Research | Feature name for signal definition and factor diagnostics. |
| Backtesting feature | Point-in-Time Backtesting | Feature name for no-lookahead strategy tests. |
| Portfolio and risk feature | Portfolio Construction & Risk | Feature name for optimizer, constraints, and risk views. |
| Reproducibility feature | Research Runs & Reports | Feature name for saved experiments and reports. |
| Frontend-only sample data | TEST DATA | Badge and data scope label for synthetic Ontology samples. |

## Right Dock Panels

| Concept | Preferred UI Term | Notes |
| --- | --- | --- |
| Activity panel | 실행 현황 | Use for the right dock activity button and panel title across pages. |
| Notification panel | 알림 | Use only for errors, warnings, confirmations, or user action required. |
| Settings panel | 설정 | Use as the generic right dock settings title unless a page-specific settings title is already established. |
