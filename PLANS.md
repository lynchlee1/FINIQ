# Completed Changes Requiring Follow-up

## 2026-08-05 — 문서 역할과 내부 구조 재정의

### Purpose

- 정상 기능과 조건부 동작을 겹치지 않게 분리한다.
- 핵심 기능이 Guide에서 빠지는 일을 막고 정적 조회 사양에는 별도 자리를 둔다.

### Implementation summary

- `behavior.md`를 `cases.md`로 바꾸고 조건에 따라 결과가 달라지는 동작만 맡겼다.
- Guide가 모든 핵심 기능과 정상 입력→결과 흐름을 한두 문장으로 설명하도록 했다.
- Reference는 경로, 자료 구조, 상태와 허용값처럼 흐름이 없는 조회 사실만 맡겼다.
- 같은 주제를 여러 파일에서 언급할 수는 있지만 조건, 결과, 값과 규칙의 본문은 한 파일만 소유하도록 정했다.
- 세 문서의 내부 골격과 선택 기준을 `diataxis/README.md`에 추가했다.

### Verification result

- 02-table의 연도별 SQLite 생성은 Guide, 중복 접수번호와 잘못된 연도 처리는 Case, 경로와 manifest 구조는 Reference로 분류되는지 대조했다.
- Guide의 기능 요약과 Case의 조건·결과가 같은 사실을 반복하지 않는지 검토했다.
- 이번 변경은 문서화 규칙만 다루므로 기존 `docs/` 파일은 새 이름과 구조로 옮기지 않았다.
- `git diff --check -- diataxis/README.md PLANS.md`를 통과했다.

## 2026-08-05 — 07단계 mode 문서 분리

### Purpose

- mode별 추출 규칙이 많은 `07-html-parse`만 하위 모듈을 갖게 한다.
- 공통 변환과 함수 책임을 mode 계약에서 분리하되 기존 문장을 빠뜨리거나 같은 계약을 복사하지 않는다.

### Implementation summary

- `07-html-parse` 루트에는 `common`, `functions`, `modes`만 연결하는 `README.md`를 두었다.
- 사채발행과 주주총회를 독립 mode로 분리하고, 유무상증자는 `common`, `paid`, `bonus`, `mixed` 하위 모듈로 나눴다.
- `asset-transaction`과 `security-transaction`은 각자 Guide와 Behavior를 갖되, 두 mode가 공유하는 결과 계약은 `raw-table`에서 한 번만 설명한다.
- mode 고유 예외가 없는 leaf에는 `reference.md`를 만들지 않고 공통 예외 사양을 연결했다.
- 공시분석 색인과 07단계 내부 링크를 새 경로로 갱신했다.

### Verification result

- 07단계 Markdown 30개를 포함한 전체 Markdown 78개가 `docs/README.md`에서 모두 도달하며 끊어진 링크는 0개였다.
- 자식 모듈이 있는 디렉터리에는 `README.md`만 있고, leaf에는 Guide와 Behavior 및 필요한 Reference만 있는지 확인했다.
- 분리 전 문서의 inline code 값은 모두 남았고, leaf 안에서 45자 이상인 같은 본문 문장이 여러 문서 유형에 중복되지 않았다.
- `git diff --check -- docs/disclosures/07-html-parse docs/disclosures/README.md PLANS.md`를 통과했다. 문서 구조와 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-08-05 — Guide·Behavior·Reference 문서 재분류

### Purpose

- 개정된 `diataxis/README.md`에 맞춰 기능 개요, 정상 동작, 예외 사양을 각각 `guides.md`, `behavior.md`, `reference.md`로 분리한다.
- `02fa9b704ad970cf9cf98f7118b8e8b031bffe5d`의 중요한 기능 계약을 잃지 않으면서 `reference.md`에 섞여 있던 정상 흐름을 옮긴다.
- 각 사실의 본문은 한 문서에만 두고 다른 문서에서는 링크한다.

### Implementation summary

- 공시분석 11개와 Ontology 5개 하위 모듈에 Guide와 Behavior를 만들었다. Guide에는 기능 개요와 사용 진입점, Behavior에는 자료 흐름·기본값·정상 처리·화면 동작만 배치했다.
- Reference에는 복구, 중단, 입력 한계와 정상 범위를 벗어난 조건만 남겼다. 정상 처리 절을 기계적으로 옮긴 뒤에도 실패 처리나 지원 한계가 남은 절은 다시 Reference로 분리했다.
- 기존 HTML 확인 절차를 공시분석 공통 Guide로 옮기고 별도 `html-download` 모듈과 새 체계에 없는 Explanation 문서를 제거했다.
- 각 모듈 색인과 교차 링크를 Guide·Behavior·Reference 경계에 맞게 갱신했다.
- `humanize-korean`으로 새 Guide 안내 문장을 검토하고 `_workspace/2026-08-05-004/final.md`에 결과를 기록했다.

### Verification result

- Markdown 51개와 하위 모듈 16개가 모두 새 파일 구조를 따르며 `docs/README.md`에서 도달한다. 끊어진 링크, 닫히지 않은 code fence, 허용되지 않은 파일명과 kebab-case 위반은 각각 0개였다.
- Behavior에 복구·중단·한계 절이 없고 Reference에 정상 동작·자료 흐름 절이 없는지 확인했다. 적용 범위를 밝히는 소스 경로를 제외하면 모듈 안에서 45자 이상인 같은 본문 문장이 여러 문서 유형에 중복되지 않았다.
- 기준 커밋의 기능 문서에 있던 inline code 값은 폐기한 분류 표지 두 개를 제외하고 모두 남았다. 숫자 표기는 `6단계`를 현재 단계명인 `06단계`로 쓴 경우만 달랐다.
- `humanize-korean` 결과는 변경률 0.00%, B등급, 자체검증 6/6이며 S1·S2 패턴이 남지 않았다.
- `git diff --check`를 통과했다. 문서만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-08-01 — Diátaxis 모듈 구조 복구

### Purpose

- `diataxis/README.md`에 적힌 모듈 우선 구조를 `docs/`에 그대로 적용한다.
- 문서 내용은 유지하면서 경로만 보고도 기능 모듈과 Tutorial, How-to guide, Reference, Explanation 역할을 구분할 수 있게 한다.

### Implementation summary

- `docs/{module}/{submodule}/{document-type}.md` 구조를 적용하고 문서 유형 디렉터리를 없앴다. 문서 유형 파일은 `tutorials.md`, `how-to-guides.md`, `reference.md`, `explanation.md`만 사용한다.
- `docs/README.md`는 세 모듈만 연결하는 중앙 지도, 각 모듈의 `README.md`는 하위 모듈과 문서 유형 파일만 연결하는 짧은 색인으로 정리했다.
- HTML parser 사양에 섞여 있던 문제 조사와 추출 규칙 변경 절을 `07-html-parse/how-to-guides.md`로 분리했다.
- 옮긴 문서의 모든 내부 링크를 새 모듈 경로에 맞게 갱신했다.

### Verification result

- 하위 모듈의 Markdown 25개가 네 문서 유형 파일명 중 하나를 사용하고 `docs/README.md`에서 도달하는지 확인했다.
- 로컬 Markdown 링크, kebab-case 디렉터리 이름, 빈 디렉터리, 문서 유형 디렉터리와 삭제한 parser README 참조를 검사했다.
- `git diff --check`를 통과했다. 문서 구조와 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-08-01 — HTML parser·Graph Viewer 문서 정리

### Purpose

- 중앙 HTML parse Reference와 package README에 겹쳐 있던 parser 계약을 한 곳에서 관리한다.
- Graph Viewer package README가 실제 workspace 경로와 명령 실행 위치를 정확히 안내하게 한다.
- 호환성이나 범위 한정 역할이 있는 문서는 근거 없이 삭제하지 않는다.

### Implementation summary

- `html_parsers/README.md`에만 있던 접수번호 stem, 저장 record·family, 제외 필드, 중간 저장, 결과 JSON 조사 순서와 실제 KIND 샘플 우선 원칙을 `docs/disclosures/07-html-parse/reference.md`와 parser 문제 해결 How-to로 옮겼다.
- 중앙 Reference와 겹치던 mode·처리 흐름 설명은 다시 복사하지 않고, 고유 내용을 옮긴 뒤 `html_parsers/README.md`를 삭제했다.
- Graph Viewer README의 app 경로를 `../../apps/graph-viewer`, 공통 package 경로를 `../theme`, `../ui`로 바로잡았다. workspace 명령은 저장소 루트에서 `frontend/`로 이동한 뒤 실행하도록 적었다.
- Claude Code 사용 여부를 확정할 수 없어 한 줄짜리 `CLAUDE.md` 호환 파일은 유지했다. `DESIGN_PRINCIPLES.md`는 package 책임을 설명하고 frontend 테스트가 직접 검사하므로 유지했으며, market-desk `AGENTS.md`도 해당 앱에만 적용되는 Next.js 지침이라 바꾸지 않았다.

### Verification result

- 없앤 parser README를 가리키는 참조가 남지 않았고 중앙 Reference에서 옮긴 고유 계약을 모두 찾을 수 있는지 확인했다.
- Graph Viewer README의 상대 경로 세 개와 공개 API 파일이 실제로 존재하는지 확인했다.
- `npm run build -w @finiq/graph-viewer`가 통과했다.
- `node --test tests/frontend/webAppDesignPrinciples.test.mjs`는 3개 모두 통과했다.
- `npm run lint -w @finiq/graph-viewer`는 기존 소스의 `any`, 미사용 변수와 React Hook 규칙 문제로 38 errors·9 warnings를 보고했다. 문서 정리 범위 밖인 기존 코드 문제라 수정하지 않았다.
- Markdown 링크 검사와 `git diff --check`를 통과했다.

## 2026-08-01 — Diátaxis 문서 최종 정리와 재검토

### Purpose

- 흩어진 기능 계약을 `docs/reference/` 한 트리에 모으고 `docs/README.md`를 유일한 중앙 문서 지도로 사용한다.
- committed 문서와 현재 기능 변경에 있던 중요 계약을 빠뜨리지 않으면서 번역투와 기계적인 기능 설명을 고친다.
- 첫 수정을 마친 뒤 별도 검사를 한 번 더 진행해 링크, 중복, 문체와 계약 보존 상태를 다시 확인한다.

### Implementation summary

- `docs/`를 Tutorial, How-to guides, Reference, Explanation 네 종류로 다시 나눴다. 기능 계약 18개는 모두 `docs/reference/` 아래에 두고, 중복 목차였던 공시분석·Ontology README와 `docs/contributing` 계열은 남기지 않았다.
- 중앙 `docs/README.md`에서 문서 25개를 모두 찾을 수 있게 했고 `diataxis/README.md`도 같은 종류 우선 구조와 단일 Reference 원칙을 설명하도록 맞췄다.
- 공통 화면 계약과 문서 작성 기준을 분리하고, 04·05단계의 같은 HTML 해시 재사용 규칙과 전용 schema가 없는 두 parser mode 계약을 각각 한 곳으로 합쳤다.
- 화면에서 할 수 없는 확인을 요구하던 01단계 How-to 문장을 실제 `알림`과 `전체 다시 받기` 흐름으로 바꿨다. 기존 HTML 신뢰와 목차 검토 절차도 실제 화면 이름과 버튼을 기준으로 다시 썼다.
- committed 상태값 계약과 주주총회 안건 시작 문자인 `[`와 `<`를 복구했다. `download_confirmation`이 01단계 설정과 충돌 내역으로 만든 hash이며 값이 달라지면 다시 확인을 요구한다는 현재 계약도 Reference에 명시했다.
- 모든 Reference 절 제목에서 기계적인 `… 기능`, `오류시 …하기` 표현을 걷어 내고, 한국어 본문은 뜻·코드명·경로·상태값·수치를 유지한 채 직접적인 동사 중심으로 고쳤다.

### Verification result

- `docs/README.md`에서 Markdown 25개에 모두 도달하며, 끊어진 링크·파일명과 다른 링크 문구·fragment 링크·빈 폴더가 0개인지 확인했다.
- committed 문서의 수치 표현은 누락 0개였다. inline code로 잡힌 값 가운데 실제 코드·문자 447개는 모두 남았고, 남지 않은 1개는 합치기 전 절 제목인 `기존 HTML 재사용 기능`이었다.
- 기능 문서에서 지정한 번역투·피동 표현이 남지 않았고, 파일별 `의`와 `등` 최대 밀도는 각각 0.904, 0.069/100자였다. 긴 문장 중복 검사는 공통 규칙을 가리키는 문장과 소스 경로 반복만 남겼다.
- `DESIGN.md`와 실제 frontend에서 `전체 다시 받기`, `현재 외부 HTML 신뢰`, `현재 내부 HTML 신뢰`, `기준 해시 생성`, `목차 조합 모아보기`, `전체 선택`, `전체 해제`, `후속 실행`, `완료` 표기를 대조했다.
- 2차 재검토에서 깨진 07단계 중단 문장과 중복된 빈 schema 계약을 찾아 고친 뒤, Markdown 괄호·공백·표·HTML anchor 검사와 `git diff --check`를 통과했다. 문서 구조와 문장만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-08-01 — 문서 anchor 제거

### Purpose

- Markdown 원문에 노출되는 명시적 HTML anchor를 사용하지 않는다.
- 문서 탐색은 파일 링크와 제목 구조만 사용한다.

### Implementation summary

- `docs/`의 `<a id="…"></a>` 태그 403개를 모두 제거했다.
- 같은 파일의 fragment 링크는 일반 텍스트로 바꾸고 다른 파일의 fragment 링크는 파일 경로만 가리키게 했다.
- `docs/README.md`에서 같은 `common/reference.md`를 가리키던 세 링크를 하나로 합쳤다.

### Verification result

- `docs/`와 parser README에 HTML anchor와 fragment 링크가 남지 않았는지 확인했다.
- 로컬 Markdown 파일 링크가 모두 이어지고 `docs/README.md`에서 문서 26개에 도달하는지 확인했다.
- 빈 폴더가 없고 `git diff --check`를 통과했다. 문서 표기와 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-07-30 — Diátaxis 문서 유형 파일 구조

### Purpose

- `docs/`의 문서 유형을 디렉터리가 아닌 `tutorials.md`, `how-to-guides.md`, `reference.md`, `explanation.md` 파일로 배치해 `diataxis/README.md`와 일치시킨다.
- 문서를 합친 뒤에도 기존 절과 링크 대상을 유지한다.

### Implementation summary

- `common`과 공시·Ontology 하위 모듈의 문서 유형 디렉터리를 같은 이름의 Markdown 파일로 바꿨다.
- `common`의 Reference 3개를 `common/reference.md`로, 07단계 Reference 10개를 `07-html-parse/reference.md`로 합쳤다. 기존 제목은 하위 절로 바꾸고 명시적 앵커는 유지했다.
- 모든 문서와 parser README의 상대 경로를 새 파일 구조에 맞게 바꾸고 비게 된 문서 유형 디렉터리를 제거했다.

### Verification result

- `docs/`의 Markdown 26개가 허용된 문서 유형 파일명이나 모듈 `README.md`를 사용하는지 확인했다.
- 문서와 parser README의 로컬 Markdown 링크 131개가 실제 파일과 앵커를 가리키고, `docs/README.md`에서 모든 문서에 도달하는지 확인했다.
- 이전 문서 유형 디렉터리 경로와 빈 폴더가 남지 않았고 `git diff --check`를 통과했다. 문서 구조와 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-07-30 — Diátaxis 작성 규칙 링크 통합

### Purpose

- `docs` 아래 README마다 Diátaxis 구조와 문서 배치 규칙을 반복하지 않는다.
- 작성 규칙은 `diataxis/README.md` 한 곳에서 관리한다.

### Implementation summary

- `docs/README.md`에서 네 문서 유형 설명과 새 문서 배치 절차를 제거하고 `diataxis/README.md` 링크로 바꿨다.
- `docs/disclosures/README.md`와 `docs/ontology/README.md`도 구조 설명 대신 같은 기준 문서를 연결하고 하위 모듈 목차만 유지했다.
- 한국어 문장 표현 기준은 별도 원본인 `writing-style.md` 링크로 유지했다.

### Verification result

- 세 README에 중복된 Diátaxis 배치 규칙이 남지 않았는지 확인했다.
- Markdown 링크 131개가 이어지고 `docs/README.md`에서 문서 37개 모두 도달 가능한지 확인했다.
- 빈 폴더가 없고 `git diff --check`를 통과하는지 확인했다. 문서 설명과 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-07-30 — 하위 모듈을 포함한 Diátaxis 문서 구조

### Purpose

- 갱신된 `diataxis/README.md`에 따라 하위 모듈이 있는 영역을 `docs/{module}/{submodule}/{diataxis-category}/{document}.md` 구조로 한 단계 더 나눈다.
- 상위 모듈의 `README.md`는 하위 모듈 링크만 담도록 간결하게 유지한다.
- 이전 구조에서 남은 빈 폴더를 모두 제거한다.

### Implementation summary

- `common`은 하위 모듈이 없는 모듈로 유지했다.
- `disclosures`는 공통·식별자 연결과 01~09단계, 04·05 공통 HTML 확인 절차를 하위 모듈로 나눴다. 07단계 변환 유형 Reference는 `07-html-parse/reference`에 함께 두었다.
- `ontology`는 공통, Quantiwise, Graph View, Chart View, 공시 분석을 `00`~`04` 하위 모듈로 나눴다.
- `docs/disclosures/README.md`와 `docs/ontology/README.md`를 하위 모듈 링크 전용 문서로 추가하고 루트 문서 지도는 이 두 문서를 가리키게 했다.
- 이전 `docs/tutorials`, `docs/how-to`, `docs/reference`, `docs/explanation`과 이동 뒤 비게 된 모듈별 종류 폴더를 제거했다.
- 모든 문서와 parser README의 링크를 새 중첩 경로로 갱신했다.

### Verification result

- 루트 문서를 제외한 Markdown 36개가 새 모듈·하위 모듈·Diátaxis 종류 경로를 따르며 빈 폴더가 하나도 없는지 확인했다.
- `docs/README.md`에서 Markdown 37개 모두 도달 가능한지 확인했다.
- 문서와 parser README의 Markdown 링크 129개가 실제 파일과 앵커를 가리키는지 확인했다.
- 기존 커밋 문서의 inline code 값 448개와 수치 표현 43개가 모두 남아 있는지 다시 대조했다.
- 이전 종류 우선 경로가 남지 않았고 `git diff --check`를 통과했다. 문서 구조와 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-07-30 — 모듈 우선 Diátaxis 문서 구조와 누락 계약 복구

### Purpose

- 저장소의 `diataxis/README.md`를 기준으로 `docs/{module}/{diataxis-category}/{document}.md` 구조를 적용한다.
- 기존 커밋 문서와 현재 작업본을 함께 대조해 기능 계약, 경로, 상태값과 수치가 빠지지 않게 한다.
- 공시 단계와 07단계 변환 유형은 번호 순서로 찾을 수 있게 유지한다.

### Implementation summary

- `docs/common`, `docs/disclosures`, `docs/ontology`를 최상위 모듈로 두고 각 문서를 `tutorials`, `how-to-guides`, `reference`, `explanation` 가운데 독자 목적에 맞는 폴더로 옮겼다.
- 공시 Reference는 공통·식별자 연결 `00`, 처리 단계 `01`~`09`, 07단계 하위 문서 `01`~`06` 번호 체계를 유지했다. Ontology Reference도 공통 `00`과 화면별 `01`~`04` 순서를 유지했다.
- `docs/README.md`를 모듈 우선 문서 지도로 다시 쓰고, 모든 문서와 지정한 Diátaxis 기준 문서를 연결했다.
- parser README가 새 공시 공통 Reference 경로를 가리키게 고쳤다.
- 1차 내용 재검토에서 빠진 Ontology 작업공간 계약을 찾아 복구했다. 공시 자료는 `01-list`부터 `07-converted`까지 표준 경로를 사용하며 Ontology 화면은 개별 단계 경로를 보내지 않는다.

### Verification result

- `docs/`의 Markdown 35개가 모두 모듈·Diátaxis 종류 경로를 따르며 `docs/README.md`에서 도달 가능한지 확인했다.
- 문서와 parser README의 Markdown 링크 138개를 검사해 모든 로컬 파일과 앵커가 이어지는지 확인했다.
- 기존 커밋 문서의 inline code 값 448개와 수치 표현 43개가 새 문서에 모두 남아 있는지 대조했다.
- 1차 재검토에서 발견한 Ontology 작업공간 누락을 고친 뒤, Tutorial·How-to guide·Reference·Explanation의 목적 구분과 번호 정렬을 2차로 다시 검토했다.
- `git diff --check`를 통과했다. 문서 구조와 Markdown 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-07-28 — 번호형 Diátaxis 문서 구조와 누락 계약 복구

### Purpose

- Tutorials, How-to guides, Reference와 Explanation을 독자 목적에 맞게 유지하면서 한 파일에 합쳐진 기능 계약을 다시 찾기 쉬운 단위로 나눈다.
- 기존 커밋 문서에는 있었지만 합본에서 빠지거나 찾기 어려워진 작문 기준, 행동 분류 기준과 세부 계약을 복구한다.
- 단계와 하위 유형은 번호로 정렬하고, 문서 링크에는 대상 파일명을 그대로 사용한다.

### Implementation summary

- 공시분석 Reference를 공통 `00`, 식별자 연결 `00`, 처리 단계 `01`~`09` 문서로 나누고, 07단계 함수와 변환 유형을 `01`~`06` 하위 문서로 구조화했다.
- Ontology Reference를 공통 `00`과 화면별 `01`~`04` 문서로 나눴다.
- 합쳐져 있던 How-to guides를 01단계 전체 기간 재다운로드, 04·05단계 기존 HTML 신뢰, 06단계 새 목차 검토 문서로 나눴다.
- 공시와 Ontology Explanation을 분리하고, Tutorial은 처음 사용하는 흐름만 순서대로 설명하도록 유지했다.
- 기존 작문 예시 전체와 행동 분류 기준을 `writing-style.md`, `behavior-classification.md`로 복구했다. 공통 화면·비동기 작업 계약은 `common-ui.md`에 모으고, 별도 저장 경로 UI 이름, 숫자 `0`, 작업 ID 복구, SQLite 세부 검증과 그래프 표시 제한을 다시 명시했다.
- 모든 문서 링크의 문구를 대상 파일명과 같게 바꾸고 parser README의 문서 경로도 새 공시 공통 Reference로 갱신했다.

### Verification result

- `docs/`의 Markdown 35개가 모두 `docs/README.md`에서 도달 가능한지 확인했다.
- 로컬 문서 링크 134개의 대상 파일, 앵커와 링크 문구를 검사했으며 누락되거나 잘못된 링크가 없었다.
- 합본 작업본의 명시적 앵커 402개 가운데 401개를 유지했다. 두 mode를 함께 가리키던 나머지 앵커 하나는 `05-asset-transaction.md`와 `06-security-transaction.md`의 독립 앵커로 교체했다.
- 기존 커밋과 합본 작업본의 기능명, 코드 식별자와 조건 문장을 대조해 빠진 계약을 복구한 뒤 수동 재검토를 한 차례 진행했다.
- Explanation 밖에 Markdown 표가 없고 `git diff --check`를 통과하는지 확인했다. 문서 구조와 Markdown 링크만 바꿨으므로 runtime 시험은 하지 않았다.

## 2026-07-28 — 문서 수 축소와 목적별 안내 통합

### Purpose

- 같은 독자 목적을 가진 문서를 영역별로 합쳐 관리할 Markdown 파일 수를 줄인다.
- Explanation에서 Markdown 표를 허용하고 Tutorials, How-to guides, Reference, Explanation 시작점을 한눈에 찾게 한다.

### Implementation summary

- 공시 단계와 parser Reference 19개를 `docs/reference/disclosures.md`, Ontology Reference 5개를 `docs/reference/ontology.md`로 합쳤다.
- 옛 파일과 제목마다 고유 앵커를 붙여 단계, 함수, 변환 유형과 화면별 사양으로 바로 이동할 수 있게 했다.
- How-to guides 3개를 `docs/how-to/disclosure-operations.md`, Explanation 2개를 `docs/explanation/architecture.md`로 합쳤다.
- Explanation 첫 표에 네 문서 목적, 핵심 질문과 시작 링크를 연결하고, 다른 문서에서는 표를 쓰지 않는 기준을 유지했다.
- Tutorial, 문서 지도와 parser README 링크를 새 파일과 앵커로 바꿨다. `resources/` 아래 파일은 읽거나 바꾸지 않았다.

### Verification result

- `docs/` 아래 Markdown 파일이 31개에서 6개로 줄었고 옛 공시 19개와 Ontology 5개 문서에 대응하는 절이 모두 남았는지 확인했다.
- 모든 로컬 링크와 앵커를 검사했으며 없앤 파일을 가리키는 경로가 남지 않았다.
- Markdown 표는 `docs/explanation/architecture.md`에만 있으며 네 문서 목적 링크를 모두 담는다.
- `git diff --check`를 통과했다. 문서만 바꿨으므로 실행 시험은 하지 않았다.

## 2026-07-28 — Diátaxis 독자 목적에 맞춘 문서 재분류

### Purpose

- 처음 배우는 흐름, 특정 문제를 푸는 절차, 정확한 사양, 설계 배경을 독자 질문에 맞는 폴더로 나눈다.
- 합친 `common.md`를 Tutorial로 옮기고 Reference에 섞인 How-to 절차를 필요한 만큼만 분리한다.

### Implementation summary

- `common.md`를 `docs/tutorials/`로 옮기고 작업공간 선택, 비동기 작업 확인, 화면 결과 구분을 차례로 익히는 Tutorial로 다시 썼다.
- 정확한 경로, 상태 수명, 표시 개수는 공시분석과 Ontology Reference의 담당 절로 옮겼다.
- 기존 Reference에 이미 있던 작업 가운데 전체 기간 재다운로드, 기존 HTML 기준 해시 만들기, 새 목차 검토하기만 How-to guides로 분리했다.
- 문서 지도, 기능 Reference, parser README가 새 위치와 담당 절을 가리키도록 고쳤다. 새 기능이나 문서에 없던 작업 절차는 만들지 않았다.
- `resources/` 아래 파일은 읽거나 바꾸지 않았다.

### Verification result

- Tutorials, How-to guides, Reference, Explanation이 각각 사용자 목적과 핵심 질문에 답하는 문서를 갖는지 확인했다.
- 옮기기 전 `common.md`에 있던 공통 흐름과 실패 표시는 Tutorial, 경로·상태 수명·표시 개수는 공시분석 또는 Ontology Reference에서 찾을 수 있는지 대조했다.
- 없앤 공통 Reference와 이전 세 계약 파일을 가리키는 링크가 남지 않았고 모든 안쪽 링크가 이어지는지 확인했다.
- 새 Tutorial과 How-to guides가 한국어 작문 기준을 지키고 `git diff --check`를 통과하는지 확인했다. 문서만 바꿨으므로 실행 시험은 하지 않았다.

## 2026-07-28 — 공통 계약 문서 통합

### Purpose

- 작업공간, 비동기 작업, 화면 표시 계약을 찾으려고 세 문서를 오가야 하는 까닭을 없앤다.

### Implementation summary

- `docs/reference/workspace.md`, `jobs.md`, `ui-conventions.md` 내용을 `docs/reference/common.md` 하나로 합쳤다.
- 기존 세 파일을 없애고 문서 지도와 parser README 링크를 새 문서로 바꿨다.
- 기존 계약값, 단계 경로, 상태 수명, 표시 개수는 그대로 두었다. `resources/` 아래 파일은 읽거나 바꾸지 않았다.

### Verification result

- 없앤 세 파일을 가리키는 Markdown 링크가 남지 않았고 새 문서 안쪽 링크와 앵커가 모두 이어지는지 확인했다.
- 통합 전 세 문서에 있던 계약 항목과 값이 새 문서에 남아 있는지 대조했다.
- `git diff --check`를 통과했다. 문서만 바꿨으므로 실행 시험은 하지 않았다.

## 2026-07-28 — 공시 처리 구조 문장 다듬기

### Purpose

- `docs/explanation/disclosure-pipeline.md`에 `geulbit/AGENTS.md` 작문 지침을 적용하되 공시 처리 계약과 코드 용어는 그대로 둔다.

### Implementation summary

- 사전에서 지정한 `정본`과 `뒤 단계`를 `원본`과 `다음 단계`로 바꿨다.
- 한자어, 번역체, 겹치는 표현을 덜어내고 낱말이 바뀐 문장은 처음부터 다시 썼다.
- 단계 번호, 파일명, 상태값, 해시 검사 규칙, 문서 링크는 바꾸지 않았다. `resources/` 아래 파일은 읽거나 바꾸지 않았다.

### Verification result

- 대상 문서가 `의`와 `등` 빈도 기준을 지키며 금지 표현 `및`, 사전 교정어 `정본`, `뒤 단계`를 쓰지 않는지 확인했다.
- 문서 안쪽 링크가 실제 파일을 가리키고 `git diff --check`를 통과하는지 확인했다.
- 설명 문서만 고쳤으므로 실행 시험은 하지 않았다.

## 2026-07-27 — Reorganized documentation with Diátaxis

### Purpose

- Replace the forced `README.md`, `logic.md` and `reference.md` layout with reader-purpose documentation.
- Restore important contracts that the uncommitted documentation compression had removed.
- Keep one central document map and one reference tree without repeating the writing guide or shared contracts.

### Implementation summary

- Rebuilt the reference tree from the complete committed disclosure and Ontology documents, then merged the newer title-search, text receipt-number and hash-verified HTML reuse contracts.
- Kept `docs/README.md` as the only documentation entry point and writing guide; removed `docs/contributing`, the old behavior-classification guide and the feature-local three-file trees.
- Moved exact behavior into `docs/reference/` and added focused explanations for the disclosure pipeline and Ontology design under `docs/explanation/`.
- Centralized workspace, asynchronous-job and display contracts, merged identical empty-schema modes, and moved shared rights-issuance schedule parsing into one contract.
- Updated the parser README to point to the new reference paths. No files under `resources/` were read or changed.

### Verification result

- Confirmed all 30 Markdown documents are reachable from `docs/README.md` and every local path and anchor resolves.
- Audited all 221 committed disclosure behavior titles: 203 remain under their original names and 18 known duplicate, shared or obsolete taxonomy headings map to consolidated contracts.
- Confirmed the uncommitted title-search format, external and internal HTML hash fields, trust actions and baseline rules remain documented.
- Confirmed no Markdown table, old taxonomy label, legacy documentation tree or duplicate contributing guide remains.
- Confirmed the maximum `의` and `등` densities are 0.834 and 0.027 per 100 characters, and the targeted Korean writing violations are absent from reference and explanation documents.
- Completed a second review that removed stale taxonomy wording, empty sections and repeated display, job, mode and schedule contracts.
- Confirmed `git diff --check` passes. Runtime tests were not run because this change only reorganizes Markdown documentation and updates one Markdown link.

## 2026-07-26 — Replaced documentation tables with readable paragraphs

### Purpose

- Remove fixed-width Markdown tables that make documentation hard to read in narrow windows.
- Preserve every mapping, condition and exact value in a vertically readable form.

### Implementation summary

- Replaced every Markdown table under `docs/` with standalone paragraphs led by a bold item or condition.
- Rewrote three-column tables as full sentences so source, format, meaning and exception context remain explicit without relying on column headers.
- Added a writing rule that keeps future documentation in paragraph form.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed no Markdown table syntax remains across 84 Markdown files under `docs/`.
- Confirmed all local links and anchors still resolve.
- Confirmed the maximum `의` and `등` densities are 0.960 and 0.099 per 100 characters and targeted translated or repeated phrases are absent.
- Confirmed `git diff --check` passes. Runtime tests were not run because this change only reformats documentation.

## 2026-07-26 — Reduced reference documents to stable contracts

### Purpose

- Keep the required `README.md`, `logic.md` and `reference.md` structure without turning `reference.md` into a complete implementation inventory.
- Give people and coding agents short decision guides, exact feature contracts and one shared source for repeated workspace, job and display rules.

### Implementation summary

- Replaced the behavior-catalogue writing rule with a placement rule that sends decisions to `logic.md`, feature-specific inputs and results to `reference.md`, repeated rules to `docs/reference/`, and routine implementation details to code and tests.
- Added shared workspace, asynchronous-job and display contracts, then linked the document map and feature contracts to them.
- Rewrote all 26 feature references around paths, accepted inputs, result structures, defaults and verification equations.
- Removed source-file-by-source-file behavior lists and the `Core`, `Serving`, `Feature`, `Fallback` and `Shutdown` catalogue headings.
- Renamed feature navigation links from `세부 기준` to `입출력 계약`.
- Applied `geulbit/AGENTS.md` writing rules to the new Korean text. No files under `resources/` were read or changed.

### Verification result

- Confirmed all 26 feature folders still contain `README.md`, `logic.md` and `reference.md`.
- Reduced feature reference documents from 2,780 lines to 701 lines; the largest reference fell from 250 lines to 48 lines.
- Confirmed no classified behavior entry or old catalogue heading remains in feature references.
- Confirmed all local links and anchors resolve across 84 Markdown files under `docs/`.
- Confirmed every overview and core-logic document stays within 21 lines.
- Confirmed the maximum `의` and `등` densities are 0.933 and 0.099 per 100 characters and targeted translated or repeated phrases are absent.
- Confirmed `git diff --check` passes. Runtime tests were not run because this change only reorganizes documentation.

## 2026-07-26 — Split readable logic from complete documentation references

### Purpose

- Make `docs/` easier to read by separating important decisions from routine behavior, exact paths, defaults and display limits.
- Give people and coding agents the same predictable `README.md`, `logic.md` and `reference.md` entry points in every functional documentation folder.

### Implementation summary

- Added a root document map and moved the shared writing guide to `docs/contributing/writing-style.md`.
- Added the same three-file structure to all 26 functional folders under `docs/disclosures` and `docs/ontology`.
- Kept each `README.md` under 30 lines as a short overview and navigation page.
- Added compact decision tables to each `logic.md` with result-changing rules, stop conditions and recovery behavior.
- Moved the complete existing behavior catalog, input paths, fields, defaults and display rules to `reference.md` without removing behavior entries.
- Updated links that previously targeted behavior headings in a `README.md` so they target the matching `reference.md`.
- Applied `geulbit/AGENTS.md` writing rules to the new Korean text. No files under `resources/` were read or changed.

### Verification result

- Confirmed all 26 functional folders contain `README.md`, `logic.md` and `reference.md`, and every reference page links back to its overview and core logic.
- Confirmed the disclosure references retain 229 classified behavior entries and 227 purpose statements.
- Confirmed all local links and referenced anchors resolve across 81 Markdown files under `docs/`.
- Confirmed every overview and core-logic document stays within 30 lines.
- Confirmed all Markdown files stay below the required `의` and `등` density limits; the maximum densities are 0.909 and 0.027 per 100 characters.
- Confirmed the targeted translated and repeated phrases do not remain outside the writing guide, and `git diff --check` passes.
- Runtime tests were not run because the change only reorganizes documentation.

## 2026-07-26 — Extended Korean writing rules across docs and the knowledge report

### Purpose

- Apply the latest `geulbit/AGENTS.md` guidance to `docs/` and `reports/knowledge-documentation/index.html` without changing documented behavior, code names, source labels, UI labels, citations, or report structure.

### Implementation summary

- Extended the shared documentation guide with rules for the dependent noun `등`, passive verb `되다`, adverb `및`, and unnecessary contrast phrasing.
- Removed prose uses of `되다` and `및`, removed unnecessary catch-all nouns after complete lists, and rewrote simple `A가 아니라 B다` comparisons.
- Replaced `하나의`, `생성`, `재생성`, and other translated or passive phrases in the report with direct Korean phrasing while preserving source names, URLs, HTML structure, CSS, and JavaScript.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed all 28 Markdown documents and the HTML report stay below the required `의` and `등` density limits; the maximum raw densities are 0.779 and 0.000 per 100 characters.
- Confirmed no prohibited passive verb, adverb, or targeted repeated and translated phrase remains in prose. Exact terms appear only where the writing guide names them or an established UI label requires them.
- Confirmed all local Markdown links, HTML anchors, local report assets, IDs, and HTML entities pass the static checks; `git diff --check` also passes.
- Browser rendering could not be checked because the browser security policy blocked the local `file://` report. No browser workaround was attempted.

## 2026-07-25 — Applied Korean writing rules to docs

### Purpose

- Apply `geulbit/AGENTS.md` guidance to the Markdown files under `docs/` without changing documented behavior, code names, source field names, or established UI labels.

### Implementation summary

- Added rules for avoiding replaceable Sino-Korean words, repeated expressions, and dense `-의` usage to the shared documentation writing guide.
- Replaced clear prose uses of `생성` and `신규` with plainer Korean, removed repeated expressions such as `각 연도별` and `하나의`, and rewrote sentences that depended heavily on `-의`.
- Kept exact code terms, JSON keys, source labels, and backticked UI labels unchanged. No files under `resources/` were read or changed.

### Verification result

- Confirmed all 28 Markdown files under `docs/` remain below one `의` per 100 characters.
- Confirmed the targeted repeated-expression scan finds no `기간동안`, `이후부터`, `각 연도별`, or `하나의`.
- Confirmed all local Markdown link targets exist and `git diff --check` passes.

## 2026-07-21 — Reimplemented stage 03 title search and filtering

### Purpose

- Implement title condition search as a direct stage 02 SQLite query without creating a new output-bearing workflow stage.
- Keep the original numbering and combine title search with filtering on the existing stage 03 page using the same action-box structure as `공시원문 외부 저장`.
- Keep a title search and its selected mode running when the user leaves the page, and keep the right-side action dock visible while scrolling.

### Implementation summary

- Added a stage 02 title-search service that compiles the shared condition blocks into SQLite predicates and performs `GROUP BY title` directly across the yearly shards with bounded parallel workers.
- Added `공시내역 제목 검색` and `공시내역 필터링` to the top action box on `/filter`, sharing the existing `공시 조건` card and workspace-owned preset store. Both modes use the existing `실행` action.
- Kept title search read-only and moved it to a background job with session-backed polling, cancellation, automatic title-mode restoration after returning to the page, and the standard right-side activity/notification dock.
- Replaced horizontal `hidden` overflow on the app scroll ancestors with `clip` so the sticky right-side action dock remains visible while the page scrolls.
- Kept filtering as automation stage 03 and restored the original seven automation stages, sidebar numbering, and canonical storage paths from `03-filter` through `09-disclosure-graph`.
- Removed the separate title-search page and its documentation, then updated disclosure indexes, ontology references, UI terminology, tests, and runtime path contracts for the restored numbering.
- No files under `resources/` were read or changed.

### Verification result

- `2 passed`: focused SQLite title-search service cases covering direct DB execution and shared boolean conditions.
- `2 passed`: focused synchronous/background title-search route cases; `20 passed`: focused frontend workflow contracts. No broad test suite was run for this reimplementation.
- The real 37-shard, 3,150,494-row workspace query returned 3,729 matching disclosures grouped into 432 titles without creating a stage 03 output file.
- Local browser verification confirmed the shared top action box, the unchanged 00-09 navigation, the sticky right-side action dock after scrolling, and automatic title-mode restoration after navigating to stage 02 and back. The verification job was cancelled afterward.
- TypeScript no-emit verification and Python bytecode compilation passed.

## 2026-07-21 — Text KIND receipt numbers in disclosure filtering

### Purpose

- Allow disclosure filtering results to retain KIND `acpt_no` identifiers containing Roman letters, as required by the disclosure identifier contract.

### Implementation summary

- Replaced the filter workflow result's digits-only `acpt_no` validation with the documented non-empty text requirement.
- Kept duplicate `acpt_no` detection and missing-identifier rejection unchanged.
- Added regression coverage for an alphanumeric `acpt_no` and an empty `acpt_no`. No files under `resources/` were read or changed.

### Verification result

- `63 passed`: complete disclosure web-app test suite, including the new alphanumeric and missing-identifier cases.
- Python bytecode compilation and `git diff --check` passed.

## 2026-07-21 — Internal HTML hash-verified reuse

### Purpose

- Reuse existing stage 05 internal HTML only when its current bytes match a recorded SHA-256 baseline.
- Let users explicitly trust externally supplied existing internal HTML and create the initial hash baseline without downloading it again.

### Implementation summary

- Added per-file `source_size_bytes` and `source_sha256` fields to the stage 05 `kind_disclosure_html_manifest.json` after internal HTML downloads and trusted-baseline creation.
- Changed stage 05 resume handling to skip only structurally valid files whose size and SHA-256 match the manifest, redownload hash mismatches, and stop when an existing file has no baseline.
- Added the `현재 내부 HTML 신뢰` confirmation and background `기준 해시 생성` action to the shared download Web UI, including verified, unverified, and mismatch counts.
- Made stage 05 automation checkpoint validation reject internal HTML whose current hash differs from its manifest baseline.
- Documented the internal HTML hash verification, trusted-baseline, manifest, and shutdown contracts and added the UI terms to `DESIGN.md`.
- Preserved the existing stage 04 integrity work and other user changes. No files under `resources/` were read or changed.

### Verification result

- `435 passed, 166 skipped, 2 deselected`: complete KIND Web service, route, disclosure automation, and resilience suites. The deselected tests are the two previously recorded unrelated failures: section-save cancellation callback timing and an external-compression fixture missing required `attachedDoc` metadata.
- `132 passed`: complete frontend contract suite.
- Python compile and `git diff --check` passed. TypeScript no-emit was not run because the workspace has no installed TypeScript compiler.

## 2026-07-21 — External HTML hash-verified reuse

### Purpose

- Reuse existing stage 04 external HTML only when its current bytes match a recorded SHA-256 baseline.
- Let users explicitly trust externally supplied existing HTML and create the initial hash baseline without downloading it again.

### Implementation summary

- Added per-file `source_size_bytes` and `source_sha256` fields to `kind_disclosure_html_manifest.json` after external HTML downloads and trusted-baseline creation.
- Changed stage 04 resume handling to skip only structurally valid files whose size and SHA-256 match the manifest, redownload mismatches, and stop when an existing file has no baseline.
- Added the `현재 외부 HTML 신뢰` confirmation and background `기준 해시 생성` action; it hashes only currently present valid targets and leaves missing new targets for the normal download.
- Added hash verification counts to existing-folder inspection and documented the external-specific reuse, trust, and shutdown contracts.
- Preserved the pre-existing user changes in `PLANS.md` and `docs/disclosures/05-internal-html-download/README.md`. No files under `resources/` were read or changed.

### Verification result

- `14 passed`: focused external HTML download, integrity-baseline, route, and resume tests.
- `44 passed, 1 deselected`: disclosure automation and resilience tests; the deselected compression fixture is unrelated to this change and already lacks required `attachedDoc` metadata.
- `386 passed, 166 skipped, 1 failed`: full KIND Web app/service suites; the one failure is the pre-existing section-save cancellation callback-count test unrelated to stage 04.
- `132 passed`: complete frontend contract suite.
- Python compile and `git diff --check` passed. TypeScript no-emit was not run because the workspace has no installed TypeScript compiler.

## 2026-07-21 — Internal HTML reuse documentation self-containment

### Purpose

- Explain the stage 05 existing-HTML reuse criterion directly in its README instead of sending readers to another document.

### Implementation summary

- Replaced the disclosure parent README link with the complete UTF-8 content check for `<html` or `openDisclsViewer`.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed the stage 05 README contains no Markdown or HTTP document links.
- `git diff --check` passed. Runtime tests were not run because the change is documentation-only.

## 2026-07-21 — Disclosure responsibility boundary correction

### Purpose

- Make Input Handling, Core Processing, and Result Validation depend on the business result declared by each document instead of a helper return value, UI state, keyword, or file's historical role.
- Re-audit every disclosure behavior against the corrected responsibility boundary.

### Implementation summary

- Rewrote the Responsibility rules around each document's declared business result and made Core Processing valid only for Core rules that produce or change its business values, membership, relationships, or ordering.
- Defined Core as the owner of business-result production and certification, and Serving as the owner of request, execution-control, and presentation lifecycles so Core Result Validation is not mistaken for Serving.
- Defined Core results as Serving inputs and reclassified every Serving display, truncation, progress, orchestration, cancellation, and recovery-routing rule from Core Processing to Input Handling.
- Defined validation metadata, manifests, warning records, and completion markers as Result Validation when they certify an unchanged completed result.
- Clarified that a prior result read by a new operation is current input, while domain extraction, result-value substitution, and incomplete-result checks are Core Processing.
- Separated invalidating an existing result and choosing a full-period input range from the normal Core download that creates replacement pages.
- Split the combined download display-count rule into missing-page display and progress-history display boundaries, and classified both as Serving Input Handling.
- Reclassified incremental search range selection as Input Handling and external HTML byte-count/SHA-256 metadata as Result Validation.
- Reordered every affected Layer/Behavior section into Input Handling, Core Processing, and Result Validation order after reclassification.
- Separated SQLite generation from manifest certification, external and internal HTML generation from manifest metadata linking, and HTML input conversion from domain-value extraction helpers.
- Split filtered-input validation from external HTML result-field extraction, and graph-input validation from graph event-date production.
- Corrected ambiguous responsibility labels for result publication, manifest linking, saved-result lookup, progress-event input, section-title extraction, rights-issuance type extraction, and graph event-date production.
- Documented reduced graph generation after missing disclosure or company identifiers as a Core Processing Fallback.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed all 20 disclosure README documents retain the same 11-heading classification structure and explicit `없음` markers for empty categories.
- Confirmed all 221 behavior entries use exactly one allowed responsibility label: 97 Input Handling, 100 Core Processing, and 24 Result Validation.
- Confirmed no Serving behavior is classified as Core Processing.
- Confirmed every Layer/Behavior section follows Input Handling → Core Processing → Result Validation order.
- Confirmed every one of the 201 adjacent behavior-entry pairs has exactly one correctly placed `<br>` separator.
- Confirmed all relative Markdown links and referenced anchors resolve.
- `git diff --check` and the `resources/` scope check passed. Runtime tests were not run because the change is documentation-only.

## 2026-07-20 — Disclosure behavior classification rewrite

### Purpose

- Rewrite every disclosure behavior document against `docs/behavior-classification-rules.md` and make classification boundaries explicit.
- Preserve every empty behavior category with its heading and an explicit `없음` entry.

### Implementation summary

- Standardized all 20 disclosure README documents as `Core` and `Serving`, each divided into `Feature`, `Fallback`, and `Shutdown`, and labeled every behavior with `Input Handling`, `Core Processing`, or `Result Validation` responsibility.
- Added the shared classification boundary to the disclosure parent document and separated normal selection, exclusion, empty-result, default-value, and review-wait behavior from unexpected-failure recovery and termination.
- Reclassified normal download defaults and correction-history value judgments as Features; classified full-period redownload, per-file parser exclusion, retries, reduced graph relationships, and display recovery as Fallbacks; and kept unsafe or incomplete execution paths as Shutdowns.
- Split mixed rules where validation, recovery, and termination had previously shared one entry, including existing-result validation, parser `skip_errors`, preview augmentation, required bond-table selection, graph input discovery, and stored-result validation.
- Re-audited the responsibility and layer boundaries after the initial rewrite: moved pre-execution KIND and pagination reads to Input Handling, separated HTML input parsing from row/result generation, treated parser warning and family checks as Core Processing, limited Result Validation to completed outputs, and moved automation orchestration from Core to Serving.
- Moved normal exclusions and default-value selection out of failure handling, including legacy preset exclusion, graph display-name priority, and correction-history threshold defaults; split the matching failure paths into their own Fallback or Shutdown rules.
- Added the complete Serving taxonomy to mode-specific parser documents and wrote `없음` in every empty Core or Serving category.
- Standardized `<br>` separators between every pair of adjacent behavior entries, including pairs separated by Feature, Fallback, Shutdown, Core, or Serving headings, and placed each separator directly after the preceding behavior content so Markdown renders it consistently.
- No files under `resources/` were read or changed.

### Verification result

- Confirmed all 20 disclosure README documents contain the same 11-heading classification sequence and no legacy `Features`, `Fallbacks`, or `Shutdowns` headings.
- Confirmed every behavior entry has one allowed responsibility label and every otherwise-empty category contains `없음`.
- Rechecked all 211 behavior entries against the three classification questions and cross-checked equivalent input, intermediate-result, completed-result, display, retry, and termination rules across documents.
- Confirmed all 191 adjacent behavior-entry pairs have exactly one `<br>` separator in the canonical `content → <br> → blank line → next heading` layout.
- Confirmed all relative Markdown links and referenced anchors in the 20 disclosure README documents resolve.
- `git diff --check` and the `resources/` scope check passed. Runtime tests were not run because the change is documentation-only.

## 2026-07-20 — Coding-style instruction relocation

### Purpose

- Make repository coding-style instructions directly available to coding agents.

### Implementation summary

- Moved the complete Coding style section from `docs/README.md` into `AGENTS.md` and merged it with the existing fallback guidance.
- Left the Writing style guidance and examples in `docs/README.md` unchanged.

### Verification result

- Confirmed the moved rules occur in `AGENTS.md` and no longer occur in `docs/README.md`.
- `git diff --check` passed for the three edited Markdown files.

## 2026-07-18 — Incremental filter review fixes

### Purpose

- Correct the implementation errors confirmed by the incremental-filter review.

### Implementation summary

- Exposed the condition-search card for automation ranges beginning at stages 04–07, where profile validation requires a saved preset.
- Preserved the pre-run canonical workflow when cancellation occurs before any source row is inspected.
- Rejected fractional incremental counts and required exact boolean `complete=false` and `passed=false` flags on interrupted results.
- Restored the missing workspace path contract, corrected the stale parser-documentation route, and removed trailing whitespace that invalidated the recorded diff check.

### Verification result

- `118 passed`: disclosure Web app, workspace, and automation suites.
- `35 passed`: focused disclosure filter service tests.
- `19 passed`: frontend path/layout contract tests.
- Python compile, TypeScript type-check, `git diff --check`, and the local Markdown-link check for 33 files passed.

## 2026-07-18 — Incremental disclosure filter workflow

### Purpose

- Keep each stage 03 condition, execution state, completed result, and interrupted partial result in one canonical workflow JSON.
- Reuse the previously inspected source count so recurring runs filter only newly appended stage 02 rows.
- Fail explicitly when source-count integrity or saved-condition integrity no longer holds.

### Implementation summary

- Embedded completed and interrupted filter results in `<data_root>/03-filter/<workflow-name>.json`; same-condition saves preserve them, while condition or mode changes reset the workflow.
- Added source offsets to the SQLite reader, count-regression checks, explicit search denominator/result numerator fields, interrupted partial-result capture, contiguous merge checks, duplicate receipt-number checks, and atomic replacement after a successful temporary merge.
- Kept `<mode>/filtered.json` as a derived stage 04 compatibility file and connected both the manual filter route and disclosure automation stage 03 to the same canonical workflow contract.
- Required automation runs from stage 03 onward to identify a saved condition-search preset and reject runtime mode or condition conflicts.
- Added the `중단됨` workflow state to the existing UI terminology and documented the count-only, append-order integrity assumptions and the deliberate absence of an unverifiable historical membership hash.
- No files under `resources/` were read or changed for this implementation.

### Verification result

- `111 passed`: disclosure Web app, workspace, and automation suites.
- `33 passed`: focused disclosure filter service tests.
- `18 passed`: frontend path/layout contract tests.
- TypeScript type-check and Python compile checks passed.

## 2026-07-17 — Documentation hierarchy normalization

### Purpose

- Match the disclosure 08, 09, and parent README structure to the established disclosure document format.
- Move rules shared by disclosure stages into `docs/disclosures/README.md` so stage documents contain only stage-specific paths, values, and behavior.
- Move rules shared by Ontology pages into `docs/ontology/README.md` and remove the same rules from child documents.

### Implementation summary

- Rebuilt the disclosure parent README with the standard Summary, Features, Fallbacks, Shutdowns, and Serving sections; normalized the 08 and 09 heading levels and moved the 09 data format under Summary details.
- Centralized the disclosure workspace and separate-directory settings, mode isolation, shared HTML reuse test, diagnostic-display contract, common job state, cancellation, empty-value display, worker default, settings persistence, and shared configuration failures.
- Left only stage-specific display counts and input/output contracts in the stage documents, moved correction-history browser rules from stage 00 to stage 08, and moved Ontology/Quantiwise display rules out of the disclosure automation document.
- Moved the former Ontology common document's rules into `docs/ontology/README.md`, added shared shard-path, worker, job-state, display, and settings rules there, and reduced `docs/ontology/common/README.md` to a compatibility link.
- Removed child duplicates for shard path resolution, missing-shard shutdown, company metadata merging, and the default date range. No files under `resources/` were read or changed.

### Verification result

- The disclosure format check confirmed that the parent, 08, and 09 documents have the same seven-heading sequence as stages 00–07.
- The parent-rule audit confirmed the selected disclosure and Ontology common rules exist in their parent document and each audited rule appears in only one file.
- All 13 disclosure Serving sections retain bold `Feature`, `Fallback`, and `Shutdown` groups in order with no nested level-four heading.
- `git diff --check` and the local Markdown-link check for all files under `docs/` passed.

## 2026-07-17 — Fallback logic documentation audit

### Purpose

- Reverify fallback and alternative-path behavior against the current code and document every reachable mechanism that was not already described under `docs/`.
- Make output loss, partial results, compression/display limits, substitutions, recovery paths, and failure boundaries explicit without changing runtime behavior.

### Implementation summary

- Updated the matching disclosure-stage and ontology README files with current behavior classified under `Features`, `Fallbacks`, or `Shutdowns`.
- Added parser and selector recovery, missing-field substitution, partial-result handling, compatibility inputs, retry and serial recovery, default source and period selection, transactional restoration, display/diagnostic limits, and lossy normalization rules.
- Reclassified frontend-only display, browser-state, and in-browser calculation behavior under `docs/disclosures/README.md`; backend response limits, stored-output behavior, parser rules, and export-affecting graph state remain in their owning stage or ontology documents.
- Rechecked two previously reported candidates against the current code and did not document them as active fallbacks: missing parse results are no longer cached as `{}`, and records without a usable sequence are skipped before the later sort default can be reached.
- Removed the previously documented random edge-ID branch after confirming that the current graph validation flow supplies missing IDs and rejects duplicate IDs before the later normalizer, making that branch unreachable for accepted graph input.
- Made documentation-only changes. No files under `resources/` were read or changed.

### Verification result

- `31 passed`: KIND JSON conversion and company classification tests.
- `2 passed`: source-preview and existing-download validation tests.
- `2 passed`: Quantiwise preview and invalid-date continuation tests. One dependency deprecation warning was reported.
- `37 passed`: focused frontend tests for correction-history display logic, fallback boundaries, ontology workspaces, and the asset Excel utility.
- `git diff --check` and the local Markdown-link check passed.

## 2026-07-17 — Policy-inconsistent fallback removal

### Purpose

- Remove newly documented fallbacks that silently alter, omit, truncate, or partially return data and therefore conflict with the repository policy of retaining only correctness- or reliability-preserving recovery.
- Keep frontend-only presentation behavior in the disclosure automation document while keeping parser, storage, and backend behavior in its owning disclosure or ontology document.

### Implementation summary

- Removed correction-matrix neighbor filling, permissive date and number salvage, the browser Triple Barrier 120-marker cap, and falsy-value display paths that hid numeric zero.
- Rejected unknown KIND search conditions, unknown saved filters, invalid canonical result-page filenames, unusable external compressed records, legacy singular merge inputs, populated invalid preview dates, dangling ontology edges, and invalid relationship weights instead of silently substituting or omitting values.
- Changed missing manifest shards, existing-download path/read errors, and market-unknown mapping-only rows under a specific market filter from partial or widened results to explicit failure or exclusion.
- Preserved an explicit company count of zero and stopped Neo4j synchronization from inventing risk metadata when the source value is null.
- Retained retries, transaction restoration, cache recomputation, bounded diagnostic display, parser recovery required for malformed KIND HTML, and serial recovery after process-pool failure because they preserve integrity without fabricating accepted output.
- Removed the raw KIND disclosure-field compatibility input; `disclosure_type_groups` is now the only accepted disclosure-type request contract, including saved workflow snapshots.
- Changed unreadable saved search conditions and broken result-page pagination from mismatch/partial-result states to explicit failures.
- Removed sectionless table-row promotion, ragged-row right padding, the 1 MiB workflow-format scan limit, receipt-number and legacy-record year inference, and the external HTML compressor's second decoder/parser pass.
- Kept the shared KIND HTML recovery parser as the single canonical reader; the external compression path now consumes that reader's result once instead of maintaining a separate recovery implementation.
- Removed partial viewer-metadata compression: external compression now requires `acptNo`, both document selects, non-empty document numbers for every option, and a selected main document instead of dropping incomplete options. Removed only the 100-byte minimum from existing-HTML detection; its identifier check and reuse behavior remain unchanged.
- Updated the owning fallback documents and focused regression tests. No files under `resources/` were read or changed.

### Verification result

- `159 passed`: focused Python suites for fallback policy, Neo4j synchronization, ontology, Quantiwise assets, integrated merge, company classification, and KIND web behavior.
- `91 passed`: KIND download, JSON conversion, result-folder exploration, company classification, pagination, and the focused fallback-policy tests after the second removal pass.
- `91 passed`: disclosure web-app, automation, and disclosure-time metadata tests.
- `486 passed, 1 deselected`: KIND web-service regression suite excluding one pre-existing cancellation callback-count test unrelated to these changes. The four fixtures that still assumed removed table correction behavior passed after being changed to canonical table structure.
- `63 passed`: KIND HTML conversion and download tests after strict viewer-metadata compression and removal of the existing-HTML 100-byte minimum.
- `10 passed`: focused fallback-policy tests, including strict selected-document validation and the single shared viewer reader.
- `35 passed, 452 deselected`: focused external HTML, viewer metadata, and compression web-service tests.
- `39 passed`: focused frontend suites for fallback boundaries, correction history, ontology workspaces, and the asset Excel utility.
- Graph viewer package build and market-desk TypeScript no-emit check passed.
- Python bytecode compilation, `git diff --check`, the local Markdown-link check for 14 changed Markdown files, and the `resources/` scope check passed.

## 2026-07-21 — Frontend dependency vulnerability patch

### Purpose

- Remove the reported high-severity denial-of-service vulnerability from the frontend development dependency tree.

### Implementation summary

- Updated the indirect development dependency `brace-expansion` from 5.0.6 to 5.0.7 in `frontend/package-lock.json` through `npm audit fix`.
- Kept the direct dependency declarations unchanged; no files under `resources/` were read or changed.

### Verification result

- `npm audit` reported zero vulnerabilities across 295 audited packages.
- `npm audit --omit=dev` reported zero production dependency vulnerabilities.
- `npm ls brace-expansion --all` resolved the ESLint dependency path to `brace-expansion@5.0.7`.

## 2026-07-21 — Disclosure filter preset compatibility and stable labels

### Purpose

- Make the existing bond-issuance, rights-issuance, and shareholder-meeting filter conditions loadable from the disclosure filtering page while preserving the original result-bearing JSON files for debugging.
- Keep the preset selector label stable instead of appending workflow state that changes over time.

### Implementation summary

- Added `database/03-filter/bond_issuance.json`, `rights_issuance.json`, and `shareholder_meeting.json` in the canonical `finiq_disclosure_filter_workflow` format.
- Copied only the six bond-issuance, two rights-issuance, and seven shareholder-meeting condition blocks; no disclosure rows, result summaries, transfer metadata, or table data were copied.
- Changed the preset selector options to show only each fixed preset name and updated the UI terminology contract accordingly; persisted workflow state remains unchanged.
- Left all three original `*_v1.json` files unchanged. No files under `resources/` were read or changed.

### Verification result

- Confirmed all three new documents satisfy the workflow loader's required format, mode, status, and step-state contract and are returned by the preset listing.
- Confirmed every condition block exactly matches its original file and the new documents contain no completed or pending filter result.
- Confirmed the focused frontend selector contract test and TypeScript type-check pass with workflow status absent from option labels.

## 2026-07-22 — Horizontal selection control redesign

### Purpose

- Reduce unused space in the MarketDesk top bar and the disclosure filter mode selector while making horizontal selection state easier to scan.

### Implementation summary

- Reorganized the top bar into one compact desktop row with an inline brand, page title, segmented navigation track, and theme action; kept the mobile header stacked and all four navigation choices on one horizontal row.
- Replaced the disclosure filter mode's empty full-width card with a responsive two-option segmented control that hugs its content on desktop and fills the available width on mobile.
- Added `aria-current` to the active top-level route, `aria-pressed` to the two filter modes, and preserved visible keyboard focus treatment.
- Documented the compact segmented-control layout rule in `DESIGN.md`. No files under `resources/` were read or changed.

### Verification result

- MarketDesk production build and shared Web app TypeScript build passed.
- All 134 frontend tests passed, including the new top-navigation and filter-mode selection contracts.
- Visual checks passed in light and dark themes at the default desktop viewport and at 390px mobile width; the page and both horizontal controls had no unintended horizontal overflow.
- `git diff --check` passed.

## 2026-07-24 — General documentation systems research report

### Purpose

- Convert the preceding documentation discussion into a coherent HTML report instead of concatenating the earlier answers.
- Compare personal knowledge systems, Q&A, current documentation, historical records, executable contracts, HTML presentation, and AI retrieval as parts of one maintainable knowledge portfolio.

### Implementation summary

- Added a standalone semantic HTML report under `reports/knowledge-documentation/` with a responsive editorial layout, light and dark color schemes, print styles, keyboard focus treatment, source references, and a locally stored generated cover image.
- Reframed minimal agent instructions as one specialized current-document type and removed project-specific recommendations at the user's request.
- Consolidated repeated claims into a source-of-truth and derived-access model covering Obsidian and Second Brain practices, PARA, evergreen notes, digital gardens, Q&A, Diátaxis, ADRs, knowledge graphs, executable documentation, HTML, RAG, translation, and maintenance habits.
- Made no changes to application behavior and did not read or change files under `resources/`.

### Verification result

- Browser rendering passed at the default 1280px desktop viewport and at 390px mobile width in the available dark color scheme.
- Confirmed all 13 table-of-contents links resolve, the cover image loads at its native 1586 by 992 resolution, no page-level horizontal overflow occurs, wide comparison tables remain locally scrollable on mobile, and browser console inspection reported no warnings or errors.
- Checked 38 external reference links: all responded successfully after updating the moved Quarto computation page, except the OpenAI page that returned an automated-client 403 while remaining a valid public URL.
- Confirmed no unescaped ampersands, no duplicate IDs, no broken internal anchors, and no visible en dash or em dash characters in the report.

## 2026-07-26 — Concise documentation-method comparison

### Purpose

- Cut the general documentation report to the smallest useful comparison.
- Rewrite the Korean copy under `geulbit/AGENTS.md` instead of shortening sentences through word substitution.

### Implementation summary

- Reduced the report from 13 chapters and 35 references to five short sections, one six-row comparison table, and eight core references.
- Kept one model: notes, current answers, historical records, executable checks, and access views.
- Rewrote visible Korean copy without `및`, the Japanese-style `-의` and `-등` constructions, or passive `-되다` forms.
- Preserved the existing cover image, semantic HTML, system light and dark themes, print styles, and responsive layout.
- Made no changes to application behavior and did not read or change files under `resources/`.

### Verification result

- Browser rendering passed at the default 1280px desktop viewport and at 390px mobile width.
- Confirmed the hero stays within two lines, the cover image loads at 1586 by 992, and the page has no horizontal overflow.
- Confirmed the comparison table scrolls inside its own container on mobile and browser console inspection reported no warnings or errors.
- `git diff --check` and the Korean-copy checks passed.

## 2026-08-01 — Diátaxis description clarification

### Purpose

- Replace an abstract tutorial description with the concrete contents expected in a tutorial.
- Remove the repeated `README.md` rule from the Diátaxis structure guide.

### Implementation summary

- Rewrote all four document definitions as short sentences and moved them into the module organization rules.
- Consolidated the two `README.md` instructions into one module-index rule.

### Verification result

- Confirmed the abstract phrase, duplicate `README.md` instruction, and separate classification table are absent.
- `git diff --check` passed.
