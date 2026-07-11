# 외부 메타데이터 병합 규칙
- 이 문서는 작성 및 검토가 완료되었으므로 사용자의 명시적 허락이 있지 않는 한 **절대로** 수정하지 않는다.

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
| `rcept_no` | N/A | DART 공시코드인 `rcept_no` 필드는 생성하지 않는다. | KIND 기반 parsing에서 사용하지 않는 식별자 |
| `acpt_no` | 입력 경로의 `Path.stem` | 확장자를 제거한 파일명 전체를 사용한다. `_`를 기준으로 자르거나 숫자 여부를 검사하지 않는다. 외부 JSON의 `acpt_no`는 같은 record를 찾는 key로만 사용한다. | - |
| `doc_no` | `compressed-external-html.json.selected_main_doc_no` | - | - |
| `corp_name` | `filtered.json`의 `company_name` | - | - |
| `상장구분` | `filtered.json`의 `market` | - | - |
| 정정공시 record의 `title` | `compressed-external-html.json.title` | - | - |
| 정정공시 묶음의 `members[].title` | `compressed-external-html.json.mainDoc.text` | - | - |
