"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Loader2, Network } from "lucide-react";
import { Button } from "@finiq/ui";
import type { GraphData } from "@finiq/graph-viewer";
import { apiPost } from "@/api/client";
import {
  HtmlWorkflowCard,
  HtmlWorkflowForm,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { useSettingsStore } from "@/store/useSettingsStore";
import { formatInteger } from "@/lib/format";
import type { OntologyNodeGraphProps } from "../graph/OntologyNodeGraph";

const OntologyNodeGraph = dynamic<OntologyNodeGraphProps>(
  () => import("../graph/OntologyNodeGraph").then((module) => module.OntologyNodeGraph),
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[620px] items-center justify-center rounded-xl border border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-sm text-[var(--tv-muted)]">
        공시 관계 그래프를 준비하는 중입니다...
      </div>
    ),
  },
);

type DisclosureGraphDocument = GraphData & {
  format: "finiq_disclosure_graph_v1";
  metadata: {
    built_at?: string;
    total_nodes?: number;
    total_edges?: number;
  };
};

type DisclosureGraphBuildResult = {
  format: "finiq_disclosure_graph_build_v1";
  output_path: string;
  source_modes: string[];
  total_nodes: number;
  total_edges: number;
};

const MODE_LABELS: Record<string, string> = {
  rights_issuance: "유무상증자",
  bond_issuance: "사채발행",
  shareholder_meeting: "주주총회",
};

export default function DisclosureGraphPage() {
  const {
    output_root: dataRoot,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [status, setStatus] = useState("그래프를 생성하거나 저장 결과를 불러오세요.");
  const [isError, setIsError] = useState(false);
  const [graphDocument, setGraphDocument] = useState<DisclosureGraphDocument | null>(null);
  const [buildResult, setBuildResult] = useState<DisclosureGraphBuildResult | null>(null);

  useEffect(() => {
    fetchSettings()
      .catch((error: Error) => {
        setStatus(error.message);
        setIsError(true);
      })
      .finally(() => setSettingsLoading(false));
  }, [fetchSettings]);

  const graphData = useMemo<GraphData | undefined>(
    () => graphDocument
      ? { nodes: graphDocument.nodes, edges: graphDocument.edges }
      : undefined,
    [graphDocument],
  );

  const requireDataRoot = () => {
    const normalized = dataRoot.trim();
    if (!normalized) {
      throw new Error("작업공간 디렉토리를 선택하세요.");
    }
    return normalized;
  };

  const loadSavedGraph = async (rootOverride?: string) => {
    const root = rootOverride ?? requireDataRoot();
    const document = await apiPost<DisclosureGraphDocument>(
      "/api/disclosures/graph/load",
      { data_root: root },
    );
    setGraphDocument(document);
    return document;
  };

  const handleBuild = async () => {
    setWorking(true);
    setIsError(false);
    setStatus("공시 관계 그래프를 생성하는 중입니다...");
    try {
      const root = requireDataRoot();
      const result = await apiPost<DisclosureGraphBuildResult>(
        "/api/disclosures/graph/build",
        { data_root: root },
      );
      setBuildResult(result);
      await loadSavedGraph(root);
      const modeLabels = result.source_modes.map((mode) => MODE_LABELS[mode] ?? mode);
      setStatus(`${modeLabels.join(", ")} 데이터를 그래프로 저장했습니다.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsError(true);
    } finally {
      setWorking(false);
    }
  };

  const handleLoad = async () => {
    setWorking(true);
    setIsError(false);
    setStatus("저장된 공시 관계 그래프를 불러오는 중입니다...");
    try {
      const document = await loadSavedGraph();
      setBuildResult(null);
      setStatus(
        `노드 ${formatInteger(document.nodes.length)}개와 엣지 ${formatInteger(document.edges.length)}개를 불러왔습니다.`,
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsError(true);
    } finally {
      setWorking(false);
    }
  };

  const fields: HtmlWorkflowField[] = [
    {
      id: "dataRoot",
      kind: "path",
      label: "작업공간 디렉토리",
      mode: "folder",
      value: dataRoot,
      onChange: (value) => saveSetting("output_root", value),
      onError: (error) => {
        setStatus(error.message);
        setIsError(true);
      },
      span: 4,
    },
  ];

  return (
    <HtmlWorkflowPage
      title="공시 관계 그래프"
      description="03단계 필터 결과와 07단계 파싱 결과를 관계 그래프 형식으로 저장하고 Obsidian 형태로 탐색합니다."
    >
      <div className="space-y-6">
        <HtmlWorkflowCard
          title="그래프 데이터"
          description="작업공간의 표준 입력을 읽어 09-disclosure-graph/disclosure-graph.json에 저장합니다."
          actions={
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={handleLoad} disabled={working || settingsLoading}>
                저장 결과 불러오기
              </Button>
              <Button type="button" onClick={handleBuild} disabled={working || settingsLoading}>
                {working ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Network className="mr-2 h-4 w-4" />}
                그래프 생성
              </Button>
            </div>
          }
        >
          <HtmlWorkflowForm fields={fields} />
          <div
            className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
              isError
                ? "border-red-300 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300"
                : "border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
            }`}
          >
            <p>{status}</p>
            {buildResult ? (
              <p className="mt-1 break-all text-xs">
                결과 데이터 경로: {buildResult.output_path}
              </p>
            ) : null}
          </div>
        </HtmlWorkflowCard>

        {graphData ? (
          <OntologyNodeGraph
            selectedCompany={null}
            panel={null}
            selectedCompanyLabel="공시 관계 그래프"
            loading={working}
            graphData={graphData}
            layoutKey="stage-09-disclosure-graph"
          />
        ) : (
          <HtmlWorkflowCard title="공시 관계 그래프" description="저장된 그래프를 불러오면 관계망이 표시됩니다.">
            <div className="flex min-h-56 items-center justify-center rounded-lg border border-dashed border-[color:var(--tv-border)] text-sm text-[var(--tv-muted)]">
              표시할 그래프가 없습니다.
            </div>
          </HtmlWorkflowCard>
        )}
      </div>
    </HtmlWorkflowPage>
  );
}
