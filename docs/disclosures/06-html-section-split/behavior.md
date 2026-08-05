# 목차 HTML 저장 정상 동작

기본 자료 흐름과 정상 실행 계약을 설명한다.

## 자료 흐름

- 입력 경로는 `<data_root>/05-internal-html-download/<mode>`, 저장 경로는 `<data_root>/06-sections`이며 저장 형식은 아래와 같다.
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

## 화면과 서비스 계약

### 정상 동작

#### 목차 선택

사용자가 저장할 목차를 직접 고른다.
- 발견한 모든 목차를 선택하지 않은 상태로 표시한다.
- 사용자는 체크박스, 전체 선택 또는 전체 해제로 저장 범위를 정한다.
- 전체 해제를 선택한 구성은 저장하지 않는다.

#### 목차 분리 표시 범위 제한

분리 결과를 바꾸지 않고 화면에 전달할 진행 내역만 제한한다.
