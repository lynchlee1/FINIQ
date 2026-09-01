export type GovernanceDisclosureStatus = "filing" | "analysis";
export type GovernanceMemoSourceKind = "authority" | "news" | "analysis" | "user";

export type GovernanceTransitionCategory = {
  id: string;
  label: string;
};

export type GovernanceComparisonPanel = {
  id: string;
  title: string;
  caption: string;
  rows: Array<{
    label: string;
    value: string;
  }>;
};

export type GovernanceTransitionEvent = {
  id: string;
  date: string;
  categoryId: string;
  status: GovernanceDisclosureStatus;
  path: string;
  scale: string;
  title: string;
  summary: string;
  evidence: string;
  sourceLabel: string;
  sourceUrl: string;
  graphNodeId: string;
};

export type GovernanceUserMemo = {
  id: string;
  date: string;
  sourceKind: GovernanceMemoSourceKind;
  path: string;
  scale: string;
  title: string;
  note: string;
  sourceLabel: string;
  sourceUrl: string;
  graphNodeId: string;
  attachedEventId?: string;
};

export type GovernanceTransitionCase = {
  id: string;
  name: string;
  market: string;
  stockCode: string;
  referenceDate: string;
  description: string;
  scopeNote: string;
  categories: GovernanceTransitionCategory[];
  comparisonPanels: GovernanceComparisonPanel[];
  events: GovernanceTransitionEvent[];
  userMemos: GovernanceUserMemo[];
  defaultEventId: string;
};
