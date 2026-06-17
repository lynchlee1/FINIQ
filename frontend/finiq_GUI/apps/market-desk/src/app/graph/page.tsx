"use client";

import dynamic from "next/dynamic";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { OntologyQuantPlatformPanel } from "./OntologyQuantPlatformPanel";

const CompanyGraphViewer = dynamic(
  () => import("@/app/company/[id]/CompanyGraphViewer").then((mod) => mod.CompanyGraphViewer),
  { ssr: false, loading: () => <PageLoadingSpinner message="로딩중..." /> }
);

export default function GraphPage() {
  return (
    <WorkflowPageShell workflowId="ontology">
      <div className="flex w-full flex-col gap-6">
        <OntologyQuantPlatformPanel />
        <CompanyGraphViewer
          companyId="demo"
          dataScopeLabel="TEST DATA"
          dataSourceLabel="Synthetic graph fixture stored in frontend source, separate from resources/"
        />
      </div>
    </WorkflowPageShell>
  );
}
