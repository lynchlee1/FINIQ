# 공통 원본 표 변환 동작

## 자료 흐름

- HTML·metadata·최종 payload 계약은 [공시원문 변환 동작](../../common/behavior.md)을 따른다.
- 두 mode 모두 전용 schema로 빈 객체를 반환한다.

## 처리 계약

### 정상 동작

#### 공통 원본 표 구조 생성

상세 추출 규칙이 없어도 다른 parser와 같은 입력·결과 흐름을 사용한다.
- 공통 식별값과 원본 `raw_tables`를 만든다.
- mode 전용 업무값, `field_parse_status`와 parser warning은 만들지 않는다.
- 직접 parser 결과의 `raw_tables`는 공통 저장 과정에서 제거한다.
