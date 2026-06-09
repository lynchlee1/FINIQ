# 실행 현황 버튼 라벨 리소스 통합 계획

## Assumptions

- "우측 버튼"은 `ActionDock`의 `실행 현황` 패널을 뜻한다.
- 현재 불일치는 실행 현황 안의 취소 버튼이 페이지별로 `중단`, `작업 중단` 등으로 흩어진 문제다.
- 기본 라벨은 더 명확한 `작업 중단`으로 통일한다.
- 특정 기능에서 다른 문구가 필요하면 공통 컴포넌트 prop으로 override한다.

## Steps

1. 공통 UI 텍스트 리소스 추가
   - `src/config/uiText.ts`에 실행 관련 기본 버튼 라벨을 둔다.
   - verify: 버튼 라벨 문자열의 기본값이 한 파일에서 조회된다.

2. `JobStatusLogger` 기본 취소 라벨 연결
   - `cancelLabel` prop을 optional로 추가하고 기본값으로 공통 리소스를 쓴다.
   - verify: 기존 호출부는 prop 추가 없이 `작업 중단`을 표시한다.

3. 실행 현황 커스텀 취소 버튼 정리
   - `download/page.tsx`처럼 `JobStatusLogger` 밖에서 직접 렌더링하는 실행 현황 취소 버튼도 같은 리소스를 쓴다.
   - verify: 실행 현황 패널 취소 버튼 문구가 `작업 중단`으로 통일된다.

4. 타입 검사 실행
   - `npm run build --workspace @finiq/app-market-desk` 또는 가능한 TypeScript 검증 명령을 실행한다.
