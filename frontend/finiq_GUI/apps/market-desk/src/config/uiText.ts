export const UI_TEXT = {
  actions: {
    cancelJob: "작업 중단",
  },
} as const;

export const SETTINGS_LABELS = {
  workerCount: "워커 수",
  parallelStrategy: "병렬 처리 방식",
  timeoutSeconds: "타임아웃 (초)",
  requestIntervalSeconds: "요청 간격 (초)",
  progressInterval: "진행 확인 간격 (건)",
  maxItems: "최대 처리 건수",
  pageSize: "페이지 크기",
  maxRequestsPerMinute: "최대 요청/분",
} as const;
