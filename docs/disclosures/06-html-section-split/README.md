### **1. Summary**

#### **기능 요약**
- KIND 본문에서 저장할 목차를 고르고 선택한 범위를 HTML로 저장하는 기능이다.

#### **세부 설명**
- 입력 경로는 `<data_root>/05-internal-html-download/<mode>`, 저장 경로는 `<data_root>/06-sections`이며, 저장 형식은 아래와 같다.
- HTML은 연도별 폴더에 저장하며 parser JSON은 만들지 않는다.

```text
<data_root>/
├── 05-internal-html-download/
│   └── <mode>/<year>/<acpt_no>.html
└── 06-sections/
    └── <year>/<acpt_no>.html
```

### **2. Core**

#### **Feature**

**[Core Processing] 목차 HTML 분리 기능**
- **목적:** KIND 본문의 목차 경계와 문서 구조를 보존한 HTML을 만든다.
- `disclosures/html_sections.py`는 `body` 바로 아래의 heading(`h1`~`h6`) 중 `SECTION-N` class를 가진 요소를 유일한 목차 경계로 사용한다.
  - 원문의 heading level, `SECTION-N`과 `id="toc_N"`의 숫자는 목차 번호로 사용하지 않는다.
  - 본문에 나온 순서대로 내부 `toc_1`, `toc_2`, ...를 부여한다.
- KIND 원문의 `SECTION-N` heading 안에 작성된 `p`가 HTML parser에서 heading 바로 다음 형제 `p`로 정규화되면 해당 `p`를 heading의 제목 요소로 사용한다.
- 각 목차 heading부터 다음 목차 heading 직전까지를 같은 section으로 저장한다.
<br>

#### **Fallback**

- 없음.

#### **Shutdown**

**[Input Handling] 목차 입력 오류시 저장 중단하기**
- **목적:** 입력이나 저장 범위를 확정하지 못한 결과를 성공으로 처리하지 않는다.
- 입력 파일을 읽거나 parsing하지 못하면 목록·요약·검사·저장 작업 전체를 실패 처리한다.
- 원문에 `head` 또는 `body`가 없거나 `body` 바로 아래에 `SECTION-N` class를 가진 heading이 없으면 실패 처리한다.
<br>

**[Core Processing] 목차 제목 확정 실패시 저장 중단하기**

- **목적:** 선택한 목차의 제목을 정해진 위치에서 찾지 못하면 section 결과를 만들지 않는다.
- 선택한 heading 및 parser가 바로 뒤로 정규화한 `p`에 제목이 없으면 실패 처리한다.
- `id="toc_N"`, heading이 아닌 `p.SECTION-N`, `.xforms_title`, heading 뒤 두 번째 이후 요소의 text와 합성한 HTML 구조는 목차나 제목을 대신하지 않는다.
- 목차 제목은 section 결과에 들어갈 업무값이므로 제목 확정 실패는 Core Processing이다.
<br>

### **3. Serving**

#### **Feature**

**[Input Handling] 목차 선택 기능**
- **목적:** 사용자가 저장할 목차를 직접 고른다.
- 발견한 모든 목차를 선택하지 않은 상태로 표시한다.
- 사용자는 체크박스, 전체 선택 또는 전체 해제로 저장 범위를 정한다.
- 전체 해제를 선택한 구성은 저장하지 않는다.
<br>

**[Core Processing] 목차 분리 표시 수**
- 최근 200줄만 보여 준다.
<br>

#### **Fallback**

- 없음.

#### **Shutdown**

**[Input Handling] 목차 선택 입력 오류시 중단하기**
- **목적:** 저장 범위를 정하지 않은 작업은 시작하지 않는다.
- 목차나 선택 결과가 없으면 실패 처리한다.
- 선택하지 않은 구성이 하나라도 있으면 저장을 시작하지 않는다.
