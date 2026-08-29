# FINIQ 문서

FINIQ는 공시 데이터를 수집·구조화하고 가격 자료와 함께 분석·시각화한다.

## 문서 안내

| 필요한 정보 | 문서 |
| --- | --- |
| 시스템 구성과 데이터 흐름 | [아키텍처](architecture.md) |
| 01~09 공시 처리 단계 | [공시 파이프라인](disclosures/index.md) |
| Quantiwise·그래프·차트·공시 분석 | [Ontology](ontology/index.md) |
| 로컬 실행, 테스트, 문서 작성 | [개발 안내](development.md) |
| 실패 진단, 복구, 재처리 | [운영 안내](operations.md) |
| UI 원칙과 공통 용어 | [디자인 시스템](design/index.md) |

## 관리 원칙

- 기능 계약을 바꾸면 관련 문서를 함께 검토하며, API와 저장 형식은 구현·테스트를 기준으로 삼는다.
- 한 단계의 설계 판단은 해당 문서, 여러 단계에 오래 영향을 주는 판단은 ADR에 남긴다.
- 미해결 항목은 `PLANS.md`, 완료 이력은 Git과 PR에서 관리한다.
