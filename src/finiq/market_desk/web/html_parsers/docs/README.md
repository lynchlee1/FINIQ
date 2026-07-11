# 공시원문 변환 규칙
- 이 문서는 작성 및 검토가 완료되었으므로 사용자의 명시적 허락이 있지 않는 한 **절대로** 수정하지 않는다.

### docs 작성 규칙
1. **이번 패치에서 명시적으로 수정 대상으로 지정되지 않은 문서 내 내용은 변경하지 않는다.**
- 오탈자, 표현 개선, 구조 정리처럼 사소해 보이는 수정이라도 사용자의 명시적 요청이 없는 한 임의로 고치지 않는다. 
- 수정이 필요하다고 판단되는 경우에는 먼저 변경 사유와 범위를 설명하고 사용자 승인을 받은 뒤 진행한다.

### 내부 문서 역할
- [external-metadata.md](./external-metadata.md): 외부 metadata 파일의 위치, 내용, 보강 방식에 대해 설명한다.
- [common-html-parser-logic-rules.md](./common/common-html-parser-logic-rules.md): HTML 파서가 공통으로 사용하는 경고 기준 로직·예외처리 로직 및 병렬 처리·미리보기 로직을 설명한다.
- [common-html-parser-data-structure.md](./common/common-html-parser-data-structure.md): 공통 표와 파일별 파싱 결과, 정정공시 묶음, 최종 저장 결과, 진단·미리보기 자료에 어떤 항목이 있고 어디에 저장되는지 설명한다.
- [common-html-parser-exception-handling.md](./common/common-html-parser-exception-handling.md): 필드 상태·경고·오류를 구분해 기록하는 공통 기준과 파일별 오류 처리, 병렬 실행 중 결과 순서·저장·중지, 미리보기·저장 조건 후보의 오류 처리 방법을 설명한다.
- [bond-issuance-parser-logic-rules.md](./bond-issuance-parser-logic-rules.md): 사채발행 공시에서 필요한 필드 추출 로직·경고 기준 로직·예외처리 로직 등을 설명한다.
- [rights-issuance-parser-logic-rules.md](./rights-issuance-parser-logic-rules.md): 유무상증자 공시에서 필요한 필드 추출 로직·경고 기준 로직·예외처리 로직 등을 설명한다.

### 프로젝트 규칙
1. **Fallback을 새로 만들기 전에는 반드시 사용자에게 승인을 요청한다.**
- 사용자의 명시적 허가 없이 예외사항을 임의로 추측하거나, 기존 요구사항을 우회하는 대체 로직을 생성하지 않는다. 
- 예외 처리가 필요하다고 판단되는 경우에는 그 이유와 예상 영향을 설명한 뒤 사용자 확인을 받은 후 진행한다.
- 여기서 fallback은 명시적으로 `fallback`이라는 이름을 사용하는 로직 외에도 **정상적인 파싱이 실패하거나 기대한 결과를 반환하지 못할 때 이를 대체하는 모든 로직**을 포함한다. 여기에는 다른 파서·선택자·데이터 소스 사용, 대체 DOM 탐색, 기본값·다른 필드 사용, 예외·검증 실패 처리, 특정 공시 형식에 대한 우회·보정 로직, 그리고 명칭과 무관하게 실질적으로 대체 경로 역할을 하는 모든 로직이 포함된다.
2. **Only SoT(Source of Truth) 원칙**
- Only SoT는 말 그대로 **유일한 출처**를 의미한다. 언급된 경우 절대로 다른 출처에 의존하지 않는다.
3. **공시 식별자 생성 규칙**
- `acpt_no`와 metadata 연결 key는 입력 경로의 `Path.stem`을 그대로 사용한다.
- `_`를 기준으로 자르거나 숫자 여부를 검사하는 대체 경로를 두지 않는다.
- KIND HTML parser와 저장 workflow는 `rcept_no` 필드를 생성하지 않는다.
4. **원문 경로 저장 규칙**
- 최종 JSON은 입력 HTML의 최상위 원문 디렉토리를 `input_directory`에 한 번만 저장한다.
- record, warning, error, preview에는 개별 파일 경로나 파일명을 저장하지 않는다. warning과 error는 `acpt_no`로 식별하고, preview는 바깥 record의 `acpt_no`를 사용한다.
5. **실제 예시와 회귀 테스트 구분**
- parsing 동작을 결정하는 실제 예시는 `resources/KIND/bond_issuance`와 `resources/KIND/rights_issuance` 아래 자료로 제한한다.
- 테스트 fixture와 합성 HTML은 이미 정한 동작의 회귀 여부만 확인한다.
