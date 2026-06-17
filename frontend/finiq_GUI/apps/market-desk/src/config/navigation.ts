export type WorkflowTab = {
  href: string;
  step: number;
  label: string;
};

export type WorkflowId =
  | "ontology"
  | "disclosure-build"
  | "html-processing"
  | "utility";

export type PageLayoutKind = "search" | "job" | "review" | "canvas";

export type WorkflowDefinition = {
  id: WorkflowId;
  label: string;
  basePath: string;
  layout: PageLayoutKind;
  steps: WorkflowTab[];
};

export type SidebarGroup = {
  label: string;
  steps: WorkflowTab[];
};

export type SidebarDefinition = {
  title: string;
  groups: SidebarGroup[];
};

export type NavItem = {
  href: string;
  label: string;
  paths: string[];
  layout: PageLayoutKind;
  workflowId?: WorkflowId;
};

export const WORKFLOWS: Record<WorkflowId, WorkflowDefinition> = {
  ontology: {
    id: "ontology",
    label: "Ontology",
    basePath: "/graph",
    layout: "canvas",
    steps: [
      { href: "/graph", step: 1, label: "Graph View" },
      { href: "/", step: 2, label: "Chart View" },
    ],
  },
  "disclosure-build": {
    id: "disclosure-build",
    label: "공시데이터 구축",
    basePath: "/download",
    layout: "job",
    steps: [
      { href: "/download", step: 1, label: "공시내역 다운로드" },
      { href: "/table", step: 2, label: "공시내역 변환" },
      { href: "/filter", step: 3, label: "공시내역 필터링" },
    ],
  },
  "html-processing": {
    id: "html-processing",
    label: "원문 처리",
    basePath: "/html-download",
    layout: "review",
    steps: [
      { href: "/html-download", step: 1, label: "공시원문 외부 저장" },
      { href: "/html-content-download", step: 2, label: "공시원문 내부 저장" },
      { href: "/html-section-split", step: 3, label: "공시원문 목차 분리" },
      { href: "/html-parse", step: 4, label: "공시원문 변환" },
      { href: "/html-change-log", step: 5, label: "공시 정정내역 한눈에" },
      { href: "/html-bond-summary", step: 6, label: "발행내역 한눈에" },
    ],
  },
  utility: {
    id: "utility",
    label: "유틸리티",
    basePath: "/utility",
    layout: "job",
    steps: [
      { href: "/utility", step: 1, label: "분할저장" },
      { href: "/utility/assets-excel", step: 2, label: "Quantiwise - Excel 미리보기" },
      { href: "/utility/assets-excel/convert", step: 3, label: "Parquet 변환하기" },
      { href: "/utility/assets-excel/parquet", step: 4, label: "Quantiwise - Parquet 미리보기" },
      { href: "/utility/assets-excel/merge", step: 5, label: "Quantiwise - 병합하기" },
    ],
  },
};

export const NAV_ITEMS: NavItem[] = [
  { href: WORKFLOWS.ontology.basePath, label: "Ontology", paths: WORKFLOWS.ontology.steps.map((tab) => tab.href), layout: "canvas", workflowId: "ontology" },
  {
    href: WORKFLOWS["disclosure-build"].basePath,
    label: WORKFLOWS["disclosure-build"].label,
    paths: [
      ...WORKFLOWS["disclosure-build"].steps.map((tab) => tab.href),
      ...WORKFLOWS["html-processing"].steps.map((tab) => tab.href),
      ...WORKFLOWS.utility.steps.map((tab) => tab.href),
    ],
    layout: WORKFLOWS["disclosure-build"].layout,
    workflowId: "disclosure-build",
  },
];

export function getWorkflowTabs(workflowId: WorkflowId): WorkflowTab[] {
  return WORKFLOWS[workflowId].steps;
}

export function getSidebarDefinition(workflowId: WorkflowId): SidebarDefinition {
  if (workflowId === "ontology") {
    return {
      title: WORKFLOWS.ontology.label,
      groups: [
        {
          label: "Ontology",
          steps: WORKFLOWS.ontology.steps,
        },
      ],
    };
  }

  const partitionStorageStep = WORKFLOWS.utility.steps[0];
  const quantiwiseSteps = [
    { ...WORKFLOWS.utility.steps[1], label: "Excel 미리보기" },
    { ...WORKFLOWS.utility.steps[2], label: "Parquet 변환하기" },
    { ...WORKFLOWS.utility.steps[3], label: "Parquet 미리보기" },
    { ...WORKFLOWS.utility.steps[4], label: "병합하기" },
  ];

  return {
    title: WORKFLOWS["disclosure-build"].label,
    groups: [
      {
        label: "공시 제목 분석",
        steps: WORKFLOWS["disclosure-build"].steps,
      },
      {
        label: "공시 내용 분석",
        steps: WORKFLOWS["html-processing"].steps,
      },
      {
        label: "유틸리티",
        steps: [partitionStorageStep],
      },
      {
        label: "Quantiwise",
        steps: quantiwiseSteps,
      },
    ],
  };
}

export function getActiveNavItem(pathname: string): NavItem | undefined {
  if (pathname.startsWith("/company/")) {
    return NAV_ITEMS.find((item) => item.workflowId === "ontology");
  }
  return NAV_ITEMS.find((item) => item.paths.includes(pathname));
}

export const ONTOLOGY_TABS = WORKFLOWS.ontology.steps;
export const BUILD_TABS = WORKFLOWS["disclosure-build"].steps;
export const HTML_PROCESS_TABS = WORKFLOWS["html-processing"].steps;
export const UTILITY_TABS = WORKFLOWS.utility.steps;
