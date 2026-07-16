export type WorkflowTab = {
  href: string;
  step: number;
  label: string;
};

export type SidebarGroup = {
  label: string;
  steps: WorkflowTab[];
  numbered?: boolean;
};

export type SidebarDefinition = {
  title: string;
  groups: SidebarGroup[];
};

export type TopbarNavItem = {
  href: string;
  label: string;
  paths?: string[];
};
