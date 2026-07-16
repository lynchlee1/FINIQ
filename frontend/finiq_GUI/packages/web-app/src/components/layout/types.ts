export type WorkflowTab = {
  href: string;
  step: number;
  label: string;
};

export type SidebarStep = Omit<WorkflowTab, "step"> & {
  step?: number;
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

export type TopbarNavItem = {
  href: string;
  label: string;
  paths?: string[];
};
