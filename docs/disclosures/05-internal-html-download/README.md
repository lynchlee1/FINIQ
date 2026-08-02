### **1. Summary**

#### **기능 요약**
- KIND 본문 HTML을 mode별·연도별로 저장하는 기능이다.

#### **세부 설명**
- 입력 경로는 `<data_root>/04-external-html-download/<mode>`, 저장 경로는 `<data_root>/05-internal-html-download/<mode>`이며, 저장 형식은 아래와 같다.
- 연도별 외부 HTML이나 `compressed-external-html.json`을 읽더라도 결과 HTML은 연도별로 저장한다.

```text
<data_root>/
├── 04-external-html-download/
│   └── <mode>/
│       ├── <year>/<acpt_no>.html
│       └── compressed-external-html.json
└── 05-internal-html-download/
    └── <mode>/
        ├── <year>/<acpt_no>.html
        └── kind_disclosure_html_manifest.json
```

### **2. Core**

#### **Feature**

**[Core Processing] 내부 HTML 저장 기능**
- **목적:** 선택한 공시의 KIND 본문 HTML을 원본 식별값과 함께 보존한다.
- 본문은 선택한 mode, 공시 연도와 접수번호를 사용해 `<mode>/<year>/<acpt_no>.html`로 저장한다.
<br>

**[Input Handling] 본문 문서 번호 기준 기능**
- **목적:** 04단계가 확정한 본문 문서 번호를 그대로 다운로드 대상에 사용한다.
- 압축 JSON을 입력할 때는 `records[].selected_main_doc_no`만 본문 문서 번호의 SoT로 사용한다.
- 연도별 외부 HTML을 직접 입력할 때도 `mainDoc`에서 명시적으로 선택된 문서 번호만 사용한다.
<br>

**[Result Validation] 다운로드 대상 무결성 검사 기능**

- **목적:** 요청 대상과 저장 결과의 접수번호 집합을 비교한다.
- 일반 실행에서는 중복·누락·추가 접수번호가 없는지 확인한다.
- 사용자가 작업을 취소한 경우에는 취소 뒤의 누락을 허용하되 저장된 항목의 중복·추가는 계속 검사한다.
<br>

#### **Fallback**

- 없음.

#### **Shutdown**

**[Input Handling] 본문 식별값 오류시 실패 처리하기**
- **목적:** 저장 경로와 다운로드 대상을 확정할 수 없는 본문을 저장하지 않는다.
- 압축 JSON의 `records[]`가 객체가 아니거나 유효한 `acpt_no`가 없으면 실패 처리한다.
- 압축 JSON의 `records[].selected_main_doc_no`가 비어 있거나 연도별 외부 HTML의 `mainDoc`에 명시적인 선택값이 없으면 실패 처리한다.
- 압축 JSON은 `records[].metadata.disclosed_at`의 ISO 날짜로만 저장 연도를 정한다. 이 값이 없거나 잘못되면 `records[].year`나 `acpt_no`로 대신하지 않고 실패 처리한다.
- 연도별 외부 HTML을 직접 입력하면 파일이 실제로 들어 있는 4자리 연도 폴더를 저장 연도로 사용한다.
- 압축 JSON의 `records[].acpt_no`에 중복이 있으면 실패 처리한다.
<br>

**[Result Validation] 다운로드 대상 검증 실패시 종료하기**
- **목적:** 요청 대상과 저장 결과가 다른 상태로 다음 단계에 진행하지 않는다.
- 일반 실행의 저장 결과에 중복·누락·추가 접수번호가 있으면 실패 처리한다.
- 사용자가 작업을 취소한 경우에도 저장 결과에 중복·추가 접수번호가 있으면 실패 처리한다.
<br>

**[Result Validation] 본문 검증 실패시 다운로드 중단하기**
- **목적:** 올바른 HTML만 결과로 남긴다.
- 새로 내려받은 본문이 HTML 판별 검사를 통과하지 못하면 방금 저장한 본문 파일을 삭제하고 실패 처리한다.
<br>

### **3. Serving**

#### **Feature**

**[Input Handling] 기존 본문 HTML 재사용 기능**
- **목적:** 이미 받은 정상 파일은 다시 다운로드하지 않는다.
- 기존 HTML이 [공통 문서](../README.md)의 `기존 HTML 재사용 기능` 판별 기준을 통과하면 다시 다운로드하지 않는다.
<br>

**[Core Processing] 내부 HTML 표시 수**
- 진행 내역은 최근 100줄만 보여 준다.
- 중복·누락·추가 접수번호는 종류별로 10개만 보여 준다.

#### **Fallback**

- 없음.

#### **Shutdown**

- 없음.
