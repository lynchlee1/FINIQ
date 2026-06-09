## 공시내역 필터링 실행 박스 정리

1. [완료] `filter/page.tsx`의 현재 실행 카드와 작업 상태 흐름을 확인한다.
   - verify: 실행 버튼이 어디에 있고, 새로고침/중단에 연결할 기존 함수가 있는지 확인한다.
2. [완료] 실행 카드에 `소스 새로고침`, `실행`, `작업 중단` 버튼을 구성한다.
   - verify: 새 버튼들이 기존 상태(`isStreaming`)와 핸들러에 맞게 활성/비활성 처리된다.
3. [완료] 프론트엔드 빌드로 변경을 검증한다.
   - verify: `npm run build`가 통과한다.

## 우측 실행 현황 작업 중단 버튼 렌더링 점검

1. [완료] `ActionDock` 사용 페이지의 우측 `실행 현황` 패널과 중단 핸들러 연결을 검사한다.
   - verify: `table`, `filter`, `utility`, `assets-excel`, `integrated-*`, `html-parse`, `html-download` 계열에서 `JobStatusLogger`의 `onCancel` 연결 여부를 확인한다.
2. [완료] 버튼이 안 보이는 원인을 렌더링 조건 기준으로 확인한다.
   - verify: 기존 `JobStatusLogger`는 `isCancellable && onCancel`일 때만 버튼을 렌더링해 실행 전에는 버튼 DOM 자체가 없음을 확인한다.
3. [완료] 공통 `JobStatusLogger`에서 `onCancel`이 있으면 `작업 중단` 버튼을 항상 렌더링하고, 실행 가능 상태가 아닐 때는 disabled 처리한다.
   - verify: 우측 `실행 현황` 패널을 쓰는 모든 페이지에 같은 렌더링 규칙이 적용된다.
4. [완료] 빌드 및 산출물로 변경을 검증한다.
   - verify: `npm --prefix frontend/finiq_GUI/apps/market-desk run build`가 통과하고, 컴파일된 Next chunk에 `onCancel` 기준 렌더링과 `disabled={!isCancellable}`이 반영된다.
