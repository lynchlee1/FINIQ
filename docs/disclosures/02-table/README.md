### **1. Summary**

#### **기능 요약**
- HTML 형식으로 저장된 KIND 조건검색 결과를 연도별 SQLite 조각으로 변환하는 기능이다.

#### **세부 설명**
- 입력 경로는 `<data_root>/01-list`, 저장 경로는 `<data_root>/02-table`이며, 저장 형식은 아래와 같다.
```text
<data_root>/
├── 01-list/
│   └── <YYYYMMDD>_<YYYYMMDD>/
│       └── *_post_page_*.body
└── 02-table/
    ├── <YYYY>.sqlite
    └── sqlite_manifest.json
```

### **2. Core**

#### **Feature**

**[Input Handling] HTML 단일 출처 사용 기능**
- **목적:** 다른 표를 읽지 않도록 구조를 하나로 고정한다.
- `summary`에 `회사명`과 `공시제목`이 모두 있는 표가 하나만 있을 때 해당 표를 읽는다.
- 공시 행은 해당 표의 유일한 직속 `tbody > tr`만 읽는다.
<br>

**[Core Processing] 연도별 SQLite 생성 기능**
- **목적:** 연도별 SQLite 조각을 생성한다.
- 각 공시일의 연도를 기준으로 SQLite 조각인 `<YYYY>.sqlite`를 생성한다.
<br>

**[Core Processing] 공시 행 중복 정리 기능**
- **목적:** 같은 공시를 한 번만 저장하면서 제거된 원본 행도 집계한다.
- 모든 원본 `tbody > tr`을 순서대로 확인한다.
- `acpt_no`가 같은 행은 같은 공시로 보고 먼저 읽은 행만 SQLite에 저장한다.
- 나중에 읽은 같은 `acpt_no` 행은 버리지 않고 중복 행 수에 포함한다.
<br>

**[Core Processing] 회사 표시 정보 추출 기능**

- **목적:** 회사 칸의 이미지 유무에 따라 시장과 badge를 명시적으로 만든다.
- 회사 칸에 이미지가 있으면 첫 번째 이미지의 `alt`를 시장으로, 나머지 이미지의 `alt`를 badge로 저장한다.
- 회사 칸에 이미지가 없으면 시장은 `null`, badge는 빈 목록으로 저장한다.
<br>

**[Result Validation] SQLite manifest 생성 기능**

- **목적:** 완성된 SQLite 조각의 출처와 검증 근거를 기록한다.
- SQLite 조각 생성이 끝나면 `sqlite_manifest.json`에 원본 경로, 테이블 이름, 전체 원본·중복·저장 행 수와 연도별 SQLite 경로·저장 행 수를 기록한다.
- 페이지별 원본 파일, 페이지 번호와 원본·중복·저장 행 수도 기록한다.
<br>

**[Result Validation] SQLite 무결성 검사 기능**
- **목적:** SQLite 조각이 제대로 생성되었는지 검사한다.
- 각 페이지의 원본 행 수가 저장 행 수와 중복 행 수의 합인지 확인한다.
- 전체 원본 행 수가 실제 SQLite 행 수와 전체 중복 행 수의 합인지 확인한다.
- 각 연도별 SQLite의 실제 행 수가 `sqlite_manifest.json`의 저장 행 수와 같은지 확인한다.
- 연도별 저장 행 수의 합이 `sqlite_manifest.json`의 전체 저장 행 수와 같은지 확인한다.
<br>

#### **Fallback**

- 없음.

#### **Shutdown**

**[Input Handling] 원본 구조 오류시 실패 처리하기**

- **목적:** 원본 페이지나 결과표의 범위를 확정할 수 없으면 변환을 중단한다.
- `<data_root>/01-list`에 `*_post_page_*.body`가 없거나 파일을 읽을 수 없는 경우 실패 처리한다.
- `kind_workflow.input.json`이 있는 연도별 입력 폴더에 공시 결과 페이지가 하나도 없거나 같은 페이지 번호의 원본 파일이 둘 이상이면 실패 처리한다.
- 공시 결과 파일명이 `_post_page_<숫자>.body`로 끝나지 않아 페이지 번호를 확정할 수 없으면 변환과 원본 직접 조회를 실패 처리한다.
- `summary`에 `회사명`과 `공시제목`이 모두 있는 표가 없거나 둘 이상이면 실패 처리한다.
- 결과표 바로 아래의 `tbody`가 없거나 둘 이상이면 실패 처리한다.
- 본문 행의 직속 `td`가 5개보다 적으면 실패 처리한다.
<br>

**[Core Processing] 공시 행 필수값 오류시 실패 처리하기**

- **목적:** 공시 행에서 SQLite에 저장할 식별값과 표시값을 확정하지 못하면 변환을 중단한다.
- 회사 칸에 유일한 `a#companysum`이 없거나 회사 ID·회사명 `title`을 읽지 못하면 실패 처리한다.
- 제목 칸에 유일한 공시 링크가 없거나 표시 제목·`acpt_no`를 읽지 못하면 실패 처리한다.
- 회사 칸에 이미지가 있으면 모든 이미지에 비어 있지 않은 `alt`가 있어야 하며, 하나라도 비어 있으면 실패 처리한다.
- 공시 링크 식별값 중 `acpt_no`는 필수값이다.
<br>

**[Input Handling] 페이지 읽기 실패시 변환 중단하기**

- **목적:** 손상된 입력을 재읽기나 복구 record로 숨기지 않는다.
- 원본 `.body`를 한 번 읽어 결과표를 확정하지 못하면 즉시 실패 처리한다. 공시 행의 필수 식별값 오류는 Core Processing 규칙에서 처리한다.
- 페이지별 pagination 값이 서로 다르거나 원본 페이지가 연속적이지 않으면 다수결이나 복구 overlay를 사용하지 않고 실패 처리한다.
- workflow metadata의 page size·요청 간 대기 시간·timeout은 모두 명시되어야 한다.
<br>

**[Input Handling] 표 생성 입력 오류시 변환 중단하기**

- **목적:** 원본과 출력 위치를 추측하지 않는다.
- 입력은 `root_directory`의 KIND 원본 폴더, 출력은 `output_path`로 명시해야 한다.
- `classification_path`, 구형 JSON classification과 이름순 파일 탐색은 지원하지 않는다.
<br>

**[Core Processing] SQLite 생성 실패시 변환 중단하기**

- **목적:** 공시 연도나 검색 표를 확정하지 못한 조각을 저장하지 않는다.
- 공시일이 네 자리 연도로 시작하지 않거나 SQLite FTS5 표를 만들 수 없으면 실패 처리한다.
<br>

**[Result Validation] 행 수 검증 실패시 변환 중단하기**

- **목적:** 원본 행이 저장 또는 중복 집계에서 빠진 결과를 사용하지 않는다.
- manifest의 각 페이지에서 원본 행 수가 저장 행 수와 중복 행 수의 합과 다르면 실패 처리한다.
- manifest의 원본 행 수가 실제 SQLite 행 수와 중복 행 수의 합과 다르면 실패 처리한다.
- manifest의 연도별 저장 행 수나 전체 저장 행 수가 실제 SQLite 행 수와 다르면 실패 처리한다.
<br>

### **3. Serving**

#### **Feature**

**[Core Processing] 무결성 오류 표시 수**
- 오류는 앞의 10개와 나머지 개수만 보여 준다.

#### **Fallback**

- 없음.

#### **Shutdown**

- 없음.
