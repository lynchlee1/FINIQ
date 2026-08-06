# 공통 원본 표 변환

## 목적

`asset_transaction`과 `security_transaction`이 함께 쓰는 원본 표 변환을 설명한다.

## 핵심 기능

### 공통 원본 표 구조 생성

상세 추출 규칙이 없어도 다른 parser와 같은 입력·결과 흐름을 사용한다.

- 공통 식별값과 원본 `raw_tables`를 만든다.

- 직접 parser 결과의 `raw_tables`는 공통 저장 과정에서 제거한다.
