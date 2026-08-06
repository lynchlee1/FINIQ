# 공시원문 변환 함수 Reference

## 구현 위치와 책임

- Web workflow 진입점은 `features/disclosures/html_parse_common.py`이며 `PARSER_REGISTRY`에서 선택한 mode parser를 찾는다.
- 메인 함수는 변환 실행, preview, 필터 후보 생성과 저장 결과 조회를 담당한다.
- 보조 함수는 HTML·표 해석, metadata·family 연결, warning과 최종 payload 구성을 담당한다.
