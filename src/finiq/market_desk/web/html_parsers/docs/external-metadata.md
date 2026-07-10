# 외부 메타데이터 병합 규칙

### 외부 메타데이터 일반 규칙
1. **Only SoC 원칙**
- 외부 메타데이터를 이용한 필드 보강은 항상 `filtered.json`, `compressed-external-html.json`만을 참고한다. 
- 절대로 `kind_disclosure_html_manifest.json`등 다른 파일에 의존하지 않는다.
2. **메타데이터 위치**
- `filtered.json`, `compressed-external-html.json`는 입력 디렉토리보다 한 단계 위에 있는 부모 디렉토리에 존재한다. 

### 외부 메타데이터 필드별 SoT
| 필드 | Only SoT | 비고 | 근거 |
|---|---|---|---|
| `title` | `compressed-external-html.json.title` | - | - |
| `rcept_no` | N/A | DART 공시코드인 `rcept_no`는 저장하거나 사용하지 않는다. | KIND 기반의 파싱 로직에서는 안정적으로 추출할 방법이 없음 |
| `acpt_no` | 입력 HTML 파일명 | `filtered.json`, `compressed-external-html.json`의 `acpt_no`는 메타데이터를 연결할 key로만 사용하고 record의 `acpt_no`에 영향을 주지 않는다. | - |
| `doc_no` | `compressed-external-html.json.selected_main_doc_no` | - | - |
| `corp_name` | `filtered.json`의 `company_name` | - | - |
| `상장구분` | `filtered.json`의 `market` | - | - |
| 정정공시 record의 `title` | `compressed-external-html.json.title` | - | - |
| 정정공시 묶음의 `members[].title` | `compressed-external-html.json.mainDoc.text` | - | - |
