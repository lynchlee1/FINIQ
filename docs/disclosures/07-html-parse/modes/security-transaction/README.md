### **1. Summary**

#### **기능 요약**
- `security_transaction` mode가 발행증권거래 공시를 공통 parser 구조로 읽는 규칙이다.

#### **세부 설명**
- HTML·metadata·최종 payload의 전체 계약은 [공시원문 변환 공통 규칙](../../README.md)을 따른다.
- 현재 mode 전용 schema는 빈 객체를 반환하므로 공통 record와 원본 `raw_tables` 외의 업무 필드를 추가하지 않는다.

### **2. Core**

#### **Feature**

**[Core Processing] 공통 원본 표 구조 생성 기능**
- **목적:** 상세 추출 규칙이 없는 현재 mode도 다른 parser와 같은 입력·결과 흐름을 사용한다.
- 공통 식별값과 원본 표 구조를 만들며 mode 전용 field status와 parser warning은 만들지 않는다.
- 직접 parser 결과의 `raw_tables`는 공통 저장 순서에서 제거된다.

#### **Fallback**

- 없음.

#### **Shutdown**

- 없음.
- 공통 중단 규칙은 [공시원문 변환의 Core Shutdown](../../README.md#shutdown)을 따른다.

### **3. Serving**

#### **Feature**

- 없음.

#### **Fallback**

- 없음.

#### **Shutdown**

- 없음.
