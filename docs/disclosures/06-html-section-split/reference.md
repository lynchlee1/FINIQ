# 목차 HTML 저장

## 기능 범위

- KIND 본문에서 목차를 골라 해당 범위를 HTML로 저장한다.

## 자료 흐름

- 입력 경로는 `<data_root>/05-internal-html-download/<mode>`, 저장 경로는 `<data_root>/06-sections`이며, 저장 형식은 아래와 같다.
- HTML은 연도별 폴더에 저장하며 parser JSON은 만들지 않는다.

```text
<data_root>/
├── 05-internal-html-download/
│   └── <mode>/<year>/<acpt_no>.html
└── 06-sections/
    └── <year>/<acpt_no>.html
```

## 처리 계약

### 정상 동작

#### 목차 HTML 분리

KIND 본문에 있는 목차 경계와 문서 구조를 보존한 HTML을 만든다.
- `disclosures/html_sections.py`는 `body` 바로 아래에서 `SECTION-N` class를 가진 heading(`h1`~`h6`)만 목차 경계로 사용한다.
  - 원문 heading level과 `SECTION-N`, `id="toc_N"`에 든 숫자는 목차 번호로 사용하지 않는다.
  - 본문에 나온 순서대로 내부 `toc_1`, `toc_2`, ...를 부여한다.
- KIND 원문에서 `SECTION-N` heading 안에 작성한 `p`가 HTML parser를 거쳐 heading 바로 다음 형제 `p`로 정규화되면, 해당 `p`를 heading 제목 요소로 사용한다.
- 각 목차 heading부터 다음 목차 heading 직전까지를 같은 section으로 저장한다.

### 중단 조건

#### 목차 입력 오류가 나면 저장 중단

입력이나 저장 범위를 확정하지 못한 결과를 성공으로 처리하지 않는다.
- 입력 파일을 읽거나 parsing하지 못하면 목록·요약·검사·저장 작업 전체를 실패 처리한다.
- 원문에 `head` 또는 `body`가 없거나 `body` 바로 아래에 `SECTION-N` class를 가진 heading이 없으면 실패 처리한다.

#### 목차 제목을 확정하지 못하면 저장 중단

선택한 목차 제목을 정해진 위치에서 찾지 못하면 section 결과를 만들지 않는다.
- 선택한 heading과 parser가 바로 뒤로 옮긴 `p`에 제목이 없으면 실패 처리한다.
- `id="toc_N"`, heading이 아닌 `p.SECTION-N`, `.xforms_title`, heading 뒤 두 번째 이후 요소에서 읽은 text와 합성한 HTML 구조는 목차나 제목을 대신하지 않는다.
- 목차 제목을 확정하지 못하면 section 결과를 만들지 않는다.

## 화면과 서비스 계약

### 정상 동작

#### 목차 선택

사용자가 저장할 목차를 직접 고른다.
- 발견한 모든 목차를 선택하지 않은 상태로 표시한다.
- 사용자는 체크박스, 전체 선택 또는 전체 해제로 저장 범위를 정한다.
- 전체 해제를 선택한 구성은 저장하지 않는다.
- 실제 작업 순서는 [처음 보는 목차 검토하기](how-to-guides.md)에서 확인한다.

#### 목차 분리 표시 범위 제한

분리 결과를 바꾸지 않고 화면에 전달할 진행 내역만 제한한다.
- 보여 주는 줄 수는 [공통 화면 사양](../../common/common-ui/reference.md)를 따른다.

### 중단 조건

#### 목차 선택 입력 오류가 나면 중단

저장 범위를 정하지 않은 작업은 시작하지 않는다.
- 목차나 선택 결과가 없으면 실패 처리한다.
- 선택하지 않은 구성이 하나라도 있으면 저장을 시작하지 않는다.
