# Completed Changes Requiring Follow-up

## 2026-07-12 — 현재 구현 정밀 검토에서 발견한 오류 수정

### Purpose

- `467d1adb..219d2c38` 변경을 HTML parser 문서 계약과 대조해 테스트만으로 드러나지 않은
  오류를 찾고 수정한다.
- 오류가 없었던 기존 검토 항목은 제거하고 실제 오류와 검증 결과만 기록한다.

### Implementation summary

- 필터 페이지의 `작업공간 디렉토리` 선택기가 파일 저장 대화상자를 열던 오류를 폴더 선택
  모드로 수정했다.
- 병렬 다운로드가 중간 페이지 누락이나 손상을 남긴 경우 파일 개수 다음 페이지가 아니라
  첫 번째 누락·손상 페이지부터 다시 내려받도록 재개 기준을 수정했다. 이미 저장된 뒤쪽
  페이지는 다시 검증·저장되어 비연속 결과가 남지 않는다.
- 두 오류를 각각 고정하는 frontend 및 Python 회귀 테스트를 추가했다.

### Verification

- 재개 및 연도 병렬 집중 Python 테스트 3건이 통과했다.
- 경로 레이아웃 frontend 테스트 14건이 통과했다.
- 전체 Python 테스트는 800건 통과·166건 환경 스킵, 전체 frontend 테스트는 93건 통과했다.
- MarketDesk TypeScript 검사, 전체 Python compile 검사와 `git diff --check`가 통과했다.
- HTML parser 문서와 `resources/`는 수정하지 않았다.
