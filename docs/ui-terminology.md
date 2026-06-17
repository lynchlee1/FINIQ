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
| Quantiwise sidebar group | Quantiwise | Use as a peer sidebar group to `외부 데이터 변환`. |
| Quantiwise preview sidebar item | 미리보기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel`. |
| Quantiwise convert sidebar item | 변환하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/convert`. |
| Quantiwise merge sidebar item | 병합하기 | Use under the `Quantiwise` sidebar group for `/utility/assets-excel/merge`. |
| Quantiwise Excel preview workflow | Quantiwise - 미리보기 | Use for the `/utility/assets-excel` navigation label and page title. |
| Quantiwise Excel convert workflow | Quantiwise - 변환하기 | Use for the `/utility/assets-excel/convert` navigation label and page title. |
| Quantiwise Parquet merge workflow | Quantiwise - 병합하기 | Use for the `/utility/assets-excel/merge` navigation label and page title. |
| Output or saved data path | 데이터 경로 | Use instead of `저장 경로` or `저장 폴더` for reusable path inputs. |
| Quantiwise conversion pre-run check | 변환 전 확인 | Use for the automatic check that scans Excel files without saving before `Quantiwise 변환`. |
| Quantiwise converted result preview | 실행 결과 | Use for the converted Parquet preview selector under the `Quantiwise - 변환하기` run card. |

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
