export type WorkflowTab = {
  href: string;
  step: number;
  label: string;
};

export type SidebarStep = Omit<WorkflowTab, "step"> & {
  step?: number;
};

export type WorkflowId =
  | "ontology"
  | "disclosure-build"
  | "html-processing"
  | "price-data"
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
  steps: SidebarStep[];
  numbered?: boolean;
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
    basePath: "/graph/chart",
    layout: "canvas",
    steps: [
      { href: "/graph/chart", step: 1, label: "Chart View" },
      { href: "/graph", step: 2, label: "Graph View" },
      { href: "/graph/analysis", step: 3, label: "공시 분석" },
    ],
  },
  "disclosure-build": {
    id: "disclosure-build",
    label: "공시데이터",
    basePath: "/disclosure-automation",
    layout: "job",
    steps: [
      { href: "/disclosure-automation", step: 0, label: "공시 자동화" },
      { href: "/download", step: 1, label: "공시내역 다운로드" },
      { href: "/table", step: 2, label: "공시내역 변환" },
      { href: "/filter", step: 3, label: "공시내역 필터링" },
    ],
  },
  "html-processing": {
    id: "html-processing",
    label: "원문 처리",
    basePath: "/external-html-download",
    layout: "review",
    steps: [
      { href: "/external-html-download", step: 4, label: "공시원문 외부 저장" },
      { href: "/internal-html-download", step: 5, label: "공시원문 내부 저장" },
      { href: "/html-section-split", step: 6, label: "공시원문 목차 분리" },
      { href: "/html-parse", step: 7, label: "공시원문 변환" },
      { href: "/html-change-log", step: 8, label: "공시 정정내역 한눈에" },
      { href: "/disclosure-graph", step: 9, label: "공시 관계 그래프" },
    ],
  },
  utility: {
    id: "utility",
    label: "유틸리티",
    basePath: "/utility",
    layout: "job",
    steps: [
      { href: "/utility", step: 1, label: "분할저장" },
    ],
  },
  "price-data": {
    id: "price-data",
    label: "주가데이터",
    basePath: "/utility/assets-excel",
    layout: "job",
    steps: [
      { href: "/utility/assets-excel", step: 1, label: "Excel 미리보기" },
      { href: "/utility/assets-excel/convert", step: 2, label: "Parquet 변환하기" },
      { href: "/utility/assets-excel/parquet", step: 3, label: "Parquet 미리보기" },
      { href: "/utility/assets-excel/merge", step: 4, label: "Parquet 병합하기" },
    ],
  },
};

export const DISCLOSURE_REVIEW_TOOLS: SidebarStep[] = [
  { href: "/html-bond-summary", label: "발행내역 한눈에" },
];

export const NAV_ITEMS: NavItem[] = [
  { href: WORKFLOWS.ontology.basePath, label: "Ontology", paths: WORKFLOWS.ontology.steps.map((tab) => tab.href), layout: "canvas", workflowId: "ontology" },
  {
    href: WORKFLOWS["disclosure-build"].basePath,
    label: WORKFLOWS["disclosure-build"].label,
    paths: [
      ...WORKFLOWS["disclosure-build"].steps.map((tab) => tab.href),
      ...WORKFLOWS["html-processing"].steps.map((tab) => tab.href),
      ...DISCLOSURE_REVIEW_TOOLS.map((tab) => tab.href),
    ],
    layout: WORKFLOWS["disclosure-build"].layout,
    workflowId: "disclosure-build",
  },
  {
    href: WORKFLOWS["price-data"].basePath,
    label: WORKFLOWS["price-data"].label,
    paths: WORKFLOWS["price-data"].steps.map((tab) => tab.href),
    layout: WORKFLOWS["price-data"].layout,
    workflowId: "price-data",
  },
  {
    href: WORKFLOWS.utility.basePath,
    label: WORKFLOWS.utility.label,
    paths: WORKFLOWS.utility.steps.map((tab) => tab.href),
    layout: WORKFLOWS.utility.layout,
    workflowId: "utility",
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

  if (workflowId === "price-data") {
    return {
      title: WORKFLOWS["price-data"].label,
      groups: [
        {
          label: "Quantiwise",
          steps: WORKFLOWS["price-data"].steps,
        },
      ],
    };
  }

  if (workflowId === "utility") {
    return {
      title: WORKFLOWS.utility.label,
      groups: [
        {
          label: "유틸리티",
          steps: WORKFLOWS.utility.steps,
        },
      ],
    };
  }

  return {
    title: WORKFLOWS["disclosure-build"].label,
    groups: [
      {
        label: "공시 자동화",
        steps: [WORKFLOWS["disclosure-build"].steps[0]],
        numbered: true,
      },
      {
        label: "공시 제목 분석",
        steps: WORKFLOWS["disclosure-build"].steps.slice(1),
        numbered: true,
      },
      {
        label: "공시 내용 분석",
        steps: WORKFLOWS["html-processing"].steps,
        numbered: true,
      },
      {
        label: "결과 검수",
        steps: DISCLOSURE_REVIEW_TOOLS,
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

export function getPageTitle(pathname: string): string | undefined {
  for (const workflow of Object.values(WORKFLOWS)) {
    const activeStep = workflow.steps.find((step) => step.href === pathname);
    if (activeStep) return activeStep.label;
  }
  const reviewTool = DISCLOSURE_REVIEW_TOOLS.find((tool) => tool.href === pathname);
  if (reviewTool) return reviewTool.label;
  return getActiveNavItem(pathname)?.label;
}

export const ONTOLOGY_TABS = WORKFLOWS.ontology.steps;
export const BUILD_TABS = WORKFLOWS["disclosure-build"].steps;
export const HTML_PROCESS_TABS = WORKFLOWS["html-processing"].steps;
export const UTILITY_TABS = WORKFLOWS.utility.steps;
export const PRICE_DATA_TABS = WORKFLOWS["price-data"].steps;
