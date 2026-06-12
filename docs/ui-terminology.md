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

