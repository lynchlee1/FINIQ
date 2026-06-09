# 공시내역 변환 SQLite manifest 개선 계획

## Assumptions

- "공시 메타데이터를 로드합니다..." 병목은 분류 JSON을 로드한 뒤 rows 전체를 만들고 다시 연도별로 그룹핑하는 변환 전처리 구간으로 본다.
- 출력 형식(`finiq_disclosure_table_manifest_v1`)과 SQLite shard schema는 유지한다.
- 새 저장 방식은 `*.sqlite_manifest_shards/` 폴더 안에 `*.sqlite_manifest.json` manifest를 두고, shard SQLite 파일도 같은 폴더에 둔다.
- 필터링 단계는 새 nested manifest 방식만 정상 저장 방식으로 본다.

## Steps

1. 변환 단계 경로 규칙 변경
   - `output_path`가 가리키는 manifest 이름은 유지하되 실제 manifest 경로를 shard 폴더 내부로 해석한다.
   - verify: 변환 결과 manifest가 `sqlite_manifest_shards` 폴더 안에 생성되고 payload 경로가 이를 가리킨다.

2. 변환 전처리 단순화 및 속도 개선
   - 분류/source folder rows를 만든 뒤 별도 `_group_rows_by_year`를 도는 대신, rows 생성 중 연도별 버킷과 summary를 같이 만든다.
   - verify: 기존 row count 검증과 shard 생성 테스트가 그대로 통과한다.

3. 필터링 단계 manifest/shard 해석 보강
   - root가 shard 폴더일 때 내부 manifest를 탐색한다.
   - root가 상위 폴더일 때 `*_shards/*.sqlite_manifest.json`만 자동 탐색한다.
   - manifest가 shard 폴더 안에 있을 때 `relative_path`가 shard 파일명인 경우 같은 폴더에서 정상 해석되게 한다.
   - verify: nested manifest directory/shard directory 테스트가 통과한다.

4. 테스트 실행
   - `pytest tests/market_desk/test_kind_web_service.py`를 실행한다.
