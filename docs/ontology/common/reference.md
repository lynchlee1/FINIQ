# Ontology 공통 사양 Reference

## 함께 쓰는 사양

### 작업공간

- 공시 자료는 [공시분석 공통 사양](../../disclosures/common/reference.md)에 정한 `01-list`부터 `07-converted`까지 표준 경로를 사용한다. Ontology 화면은 개별 단계 경로를 보내지 않는다.
- `작업공간 디렉토리` 아래 `database/00-stock`에 주가 자료를 둔다.
- 항목별 Parquet은 `database/00-stock/by_item`에 둔다.

### 비동기 작업

- 진행 내역 최근 100줄을 메모리에 보관한다.
- 끝난 작업은 마지막 갱신 뒤 기본 60분이 지나면 메모리에서 지운다.

### 화면 표시

- 공통 표시 규칙은 [공시분석 공통 사양](../../disclosures/common/reference.md), 비동기 작업 복구 규칙은 [공시분석 사례](../../disclosures/common/cases.md)를 따른다.
- 빈 값은 문맥에 따라 `-` 또는 `N/A`로 표시하고 숫자 `0`은 그대로 표시한다.

### 회사 검색 결과

- Quantiwise 가격 mapping에만 있는 회사도 검색 결과에 포함한다.
- 추가 회사의 시장·공시일은 빈 값, 공시 건수는 0이며 가격 자료 보유 여부는 참으로 표시한다.

### 진행 내역

**Ontology 작업** — 최근 100줄

**Quantiwise** — 최근 30줄

### 결과 예시

**회사 badge** — 3개

**그래프 방문 기록** — 10개

**Quantiwise 계정 문제** — 5개

**Quantiwise 미리보기** — 12열

**Quantiwise 중복·불일치 항목** — 20개
