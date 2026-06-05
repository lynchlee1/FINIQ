"use client";

import dynamic from "next/dynamic";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";

const CompanyGraphViewer = dynamic(
  () => import("@/app/company/[id]/CompanyGraphViewer").then((mod) => mod.CompanyGraphViewer),
  { ssr: false, loading: () => <PageLoadingSpinner message="로딩중..." /> }
);

export default function GraphPage() {
  return (
    <WorkflowPageShell workflowId="ontology">
      <div className="flex flex-col gap-6 w-full h-[calc(100vh-140px)]">
        <CompanyGraphViewer companyId="demo" />
      </div>
    </WorkflowPageShell>
  );
}
