## 공시내역 필터링 결과 영역 정리

목적:
- 공시내역 필터링 페이지의 결과 영역에서 실제 확인에 필요 없는 요약 정보 박스와 JSON 원문 미리보기를 제거한다.
- 필터 결과 테이블과 페이지 이동 기능은 유지해 화면을 더 단순하게 만든다.

작성한 코드:
- `frontend/finiq_GUI/apps/market-desk/src/app/filter/page.tsx`
  - `필터 결과` 카드 아래의 요약 정보 박스 렌더링을 삭제했다.
  - 요약 정보 박스 전용 계산값인 `companyCount`를 삭제했다.
  - 하단 JSON 미리보기 `<pre>` 렌더링을 삭제했다.
  - JSON 미리보기 전용 `jsonPreview` 계산을 삭제했다.

검증:
- `npm run build --workspace @finiq/app-market-desk`
  - 통과.
