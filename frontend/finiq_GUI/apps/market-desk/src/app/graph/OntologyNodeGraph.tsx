"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { Braces, Download, Eye, FileCode2, FileJson, ImageDown, LineChart, MapPin, Redo2, Save, Search, Undo2, Unlock, XCircle } from "lucide-react";
import {
  DEFAULT_LAYOUT,
  DEFAULT_STYLE,
  GraphCanvas,
  SettingsPanel,
  STYLE_PRESETS,
  exportCanvasPng,
  exportGraphJson,
  exportLayoutJson,
  exportStyleJson,
  exportVisibleSvg,
  shortestPath,
  useGraphViewer,
  type GraphData,
  type GraphEdge,
  type GraphNode,
} from "@finiq/graph-viewer";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@finiq/ui";
import { ActionDock, JobStatusLogger, PageLoadingSpinner } from "@finiq/web-app/status";
import { formatInteger } from "@/lib/format";
import type { OntologyCompany, OntologyPanel } from "./OntologyGraphWorkspace";

export type OntologyNodeGraphProps = {
  selectedCompany: OntologyCompany | null;
  panel: OntologyPanel | null;
  selectedCompanyLabel: string;
  loading: boolean;
  graphData?: GraphData;
  layoutKey?: string;
};

function graphNodeId(prefix: string, value: string) {
  return `${prefix}:${value.replace(/[^a-zA-Z0-9가-힣_-]+/g, "-") || "unknown"}`;
}

function buildOntologyGraphData(
  company: OntologyCompany | null,
  panel: OntologyPanel | null,
  selectedCompanyLabel: string,
): GraphData {
  const companyId = company?.stock_code || panel?.company.stock_code || "ontology";
  const companyNodeId = graphNodeId("company", companyId);
  const nodes: GraphNode[] = [
    {
      id: companyNodeId,
      label: selectedCompanyLabel,
      type: "Company",
      group: "company",
      tags: [company?.market || panel?.company.market || "전체"],
      properties: {
        stock_code: companyId,
        disclosure_count: company?.disclosure_count ?? panel?.summary.visible_disclosures ?? 0,
      },
    },
  ];
  const edges: GraphEdge[] = [];
  const groupNodeIds = new Map<string, string>();
  const groupCounts = new Map<string, number>();

  for (const group of panel?.chart.groups ?? []) {
    groupCounts.set(group.name, group.count);
  }
  for (const item of panel?.timeline ?? []) {
    groupCounts.set(item.group, groupCounts.get(item.group) ?? 0);
  }

  for (const [groupName, count] of groupCounts) {
    const groupNodeId = graphNodeId("group", groupName);
    groupNodeIds.set(groupName, groupNodeId);
    nodes.push({
      id: groupNodeId,
      label: groupName,
      type: "DisclosureGroup",
      group: groupName,
      tags: ["공시그룹"],
      properties: { count },
    });
    edges.push({
      id: `edge:${companyNodeId}->${groupNodeId}`,
      source: companyNodeId,
      target: groupNodeId,
      relation: "HAS_DISCLOSURE_GROUP",
      category: "ontology",
      weight: Math.max(1, count),
      directed: true,
      properties: {},
    });
  }

  for (const [index, item] of (panel?.timeline ?? []).slice(0, 80).entries()) {
    const eventNodeId = graphNodeId("disclosure", item.acpt_no || `${item.disclosed_at}-${index}`);
    const groupNodeId = groupNodeIds.get(item.group) ?? companyNodeId;
    nodes.push({
      id: eventNodeId,
      label: item.title || item.acpt_no || "공시",
      type: "Disclosure",
      group: item.group,
      tags: [item.trade_day ? "차트마커" : "마커없음"],
      properties: {
        disclosed_at: item.disclosed_at,
        trade_day: item.trade_day,
        submitter: item.submitter,
        acpt_no: item.acpt_no,
      },
    });
    edges.push({
      id: `edge:${groupNodeId}->${eventNodeId}`,
      source: groupNodeId,
      target: eventNodeId,
      relation: "CONTAINS_DISCLOSURE",
      category: "event",
      weight: 1,
      directed: true,
      properties: {},
    });
  }

  return { nodes, edges };
}

export function OntologyNodeGraph({ selectedCompany, panel, selectedCompanyLabel, loading, graphData, layoutKey }: OntologyNodeGraphProps) {
  const graphFrameRef = useRef<HTMLDivElement | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const [jumpToNodeId, setJumpToNodeId] = useState<string | undefined>(undefined);
  const ontologyGraph = useMemo(
    () => graphData ?? buildOntologyGraphData(selectedCompany, panel, selectedCompanyLabel),
    [graphData, panel, selectedCompany, selectedCompanyLabel],
  );
  const {
    graph,
    visibleGraph,
    visibleDegreeMap,
    style,
    stylePresets,
    layout,
    selectedNodeIds,
    selectedEdgeIds,
    highlightedNodeIds,
    highlightedEdgeIds,
    simulationRunning,
    onNodeClick,
    onEdgeClick,
    onBackgroundClick,
    onNodeHover,
    onContextAction,
    onVisibleBounds,
    replaceGraph,
    setSearchText,
    setStyle,
    setGraph,
    nodeTypes,
    filters,
    updateFilters,
    updateLayout,
    applyPreset,
    savePreset,
    setSimulationRunning,
    undo,
    redo,
    canUndo,
    canRedo,
    unpinAllNodes,
    showAll,
  } = useGraphViewer({
    initialTheme: "dark",
    initialStyle: STYLE_PRESETS["Obsidian-like"] ?? DEFAULT_STYLE,
    initialLayout: { ...DEFAULT_LAYOUT, chargeStrength: -320, linkDistance: 90 },
    themePresetNames: { light: "Obsidian-like", dark: "Obsidian-like" },
  });
  const selectedNode = useMemo(() => {
    const nodeId = Array.from(selectedNodeIds)[0];
    return nodeId ? visibleGraph.nodes.find((node) => node.id === nodeId) ?? null : null;
  }, [selectedNodeIds, visibleGraph.nodes]);
  const selectedEdge = useMemo(() => {
    const edgeId = Array.from(selectedEdgeIds)[0];
    return edgeId ? visibleGraph.edges.find((edge) => edge.id === edgeId) ?? null : null;
  }, [selectedEdgeIds, visibleGraph.edges]);
  const selectedPath = useMemo(
    () =>
      selectedNodeIds.size === 2
        ? shortestPath(graph, Array.from(selectedNodeIds)[0], Array.from(selectedNodeIds)[1])
        : [],
    [graph, selectedNodeIds],
  );

  useEffect(() => {
    replaceGraph(ontologyGraph);
  }, [ontologyGraph, replaceGraph]);

  const handleSearchChange = (event: ChangeEvent<HTMLInputElement>) => {
    setSearchValue(event.target.value);
    setSearchText(event.target.value);
  };
  const toggleNodeTypeFilter = (type: string) => {
    const nextNodeTypes = filters.nodeTypes.includes(type)
      ? filters.nodeTypes.filter((nodeType) => nodeType !== type)
      : [...filters.nodeTypes, type];
    updateFilters({ ...filters, nodeTypes: nextNodeTypes });
  };
  const layoutKeySuffix = layoutKey || selectedCompany?.stock_code || panel?.company.stock_code || "default";
  const handleSaveLayout = () => {
    const layoutState = visibleGraph.nodes.map((node) => ({
      id: node.id,
      fx: node.fx,
      fy: node.fy,
      pinned: node.pinned,
    }));
    localStorage.setItem(`ontology_graph_layout_${layoutKeySuffix}`, JSON.stringify(layoutState));
  };
  const handleLoadLayout = () => {
    const saved = localStorage.getItem(`ontology_graph_layout_${layoutKeySuffix}`);
    if (!saved) return;
    const layoutState = JSON.parse(saved) as Array<{ id: string; fx?: number; fy?: number; pinned?: boolean }>;
    const layoutMap = new Map(layoutState.map((node) => [node.id, node]));
    replaceGraph({
      nodes: graph.nodes.map((node) => {
        const savedNode = layoutMap.get(node.id);
        if (savedNode?.pinned) {
          return {
            ...node,
            fx: savedNode.fx,
            fy: savedNode.fy,
            x: savedNode.fx,
            y: savedNode.fy,
            pinned: true,
          };
        }
        return node;
      }),
      edges: graph.edges,
    });
  };
  const handleHideSelected = () => {
    selectedNodeIds.forEach((nodeId) => onContextAction("node", nodeId, "hide"));
    selectedEdgeIds.forEach((edgeId) => onContextAction("edge", edgeId, "hide"));
  };
  const handleApplyNeighborhood = () => {
    const nodeId = Array.from(selectedNodeIds)[0];
    if (nodeId) onContextAction("node", nodeId, "neighbors");
  };
  const handleJumpSelected = () => {
    const nodeId = Array.from(selectedNodeIds)[0];
    if (!nodeId) return;
    setJumpToNodeId(undefined);
    requestAnimationFrame(() => setJumpToNodeId(nodeId));
  };
  const handleNodePatch = (nodeId: string, patch: Partial<GraphNode>) => {
    setGraph((current) => ({
      nodes: current.nodes.map((node) => (node.id === nodeId ? { ...node, ...patch } : node)),
      edges: current.edges,
    }));
  };
  const handleEdgePatch = (edgeId: string, patch: Partial<GraphEdge>) => {
    setGraph((current) => ({
      nodes: current.nodes,
      edges: current.edges.map((edge) => (edge.id === edgeId ? { ...edge, ...patch } : edge)),
    }));
  };
  const handleDeleteSelectedNode = (nodeId: string) => {
    onContextAction("node", nodeId, "delete");
  };
  const handleDeleteSelectedEdge = (edgeId: string) => {
    onContextAction("edge", edgeId, "delete");
  };
  const handleExportPng = () => {
    const canvas = graphFrameRef.current?.querySelector("canvas");
    if (canvas instanceof HTMLCanvasElement) {
      exportCanvasPng(canvas, `ontology-graph-${layoutKeySuffix}.png`);
    }
  };
  const selectedNodeCount = selectedNodeIds.size;
  const selectedEdgeCount = selectedEdgeIds.size;

  return (
    <div className="relative action-dock-host flex w-full flex-col gap-4 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
    <Card className="ontology-card">
      <CardHeader className="ontology-page-card-header">
        <div className="space-y-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <CardTitle className="ontology-card-title flex items-center gap-2">
              <LineChart className="h-4 w-4" />
              공시 관계 그래프
            </CardTitle>
            <div className="ontology-action-row">
              {nodeTypes.map((type) => {
                const isActive = filters.nodeTypes.length === 0 || filters.nodeTypes.includes(type);
                return (
                  <Button
                    key={type}
                    type="button"
                    variant={isActive ? "default" : "outline"}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => toggleNodeTypeFilter(type)}
                  >
                    {type}
                  </Button>
                );
              })}
            </div>
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(240px,0.8fr)_minmax(320px,1fr)_auto_auto] xl:items-center">
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="ontology-metric ontology-panel-section py-1.5">
                <p className="ontology-muted">노드</p>
                <p className="font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(visibleGraph.nodes.length)}</p>
              </div>
              <div className="ontology-metric ontology-panel-section py-1.5">
                <p className="ontology-muted">엣지</p>
                <p className="font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(visibleGraph.edges.length)}</p>
              </div>
              <div className="ontology-metric ontology-panel-section py-1.5">
                <p className="ontology-muted">선택</p>
                <p className="font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(selectedNodeCount + selectedEdgeCount)}</p>
              </div>
            </div>
              <div className="relative min-w-0">
                <Search className="absolute left-2.5 top-2 h-4 w-4 text-slate-500 dark:text-slate-400" />
                <Input
                  aria-label="노드 검색"
                  placeholder="노드 검색"
                  value={searchValue}
                  onChange={handleSearchChange}
                  className="h-8 w-full pl-9 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100"
                />
              </div>
              <div className="ontology-toolbar flex items-center gap-1 p-1">
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="실행 취소" onClick={undo} disabled={!canUndo}>
                  <Undo2 className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="다시 실행" onClick={redo} disabled={!canRedo}>
                  <Redo2 className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="숨김 초기화" onClick={showAll}>
                  <Eye className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="핀 해제" onClick={unpinAllNodes}>
                  <Unlock className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="현재 레이아웃 저장" onClick={handleSaveLayout}>
                  <Save className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="저장된 레이아웃 불러오기" onClick={handleLoadLayout}>
                  <Download className="h-4 w-4" />
                </Button>
              </div>
              <div className="ontology-toolbar flex items-center gap-1 p-1">
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="그래프 JSON 내보내기" onClick={() => exportGraphJson(graph, `ontology-graph-${layoutKeySuffix}.json`)}>
                  <FileJson className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="스타일 JSON 내보내기" onClick={() => exportStyleJson(style, `ontology-graph-style-${layoutKeySuffix}.json`)}>
                  <Braces className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="레이아웃 JSON 내보내기" onClick={() => exportLayoutJson(graph, `ontology-graph-layout-${layoutKeySuffix}.json`)}>
                  <FileCode2 className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="SVG 내보내기" onClick={() => exportVisibleSvg(visibleGraph, 1280, 720, style.backgroundColor, `ontology-graph-${layoutKeySuffix}.svg`)}>
                  <FileCode2 className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-300" title="PNG 내보내기" onClick={handleExportPng}>
                  <ImageDown className="h-4 w-4" />
                </Button>
              </div>
          </div>
        </div>
      </CardHeader>
      <CardContent ref={graphFrameRef} className="relative h-[min(72vh,760px)] min-h-[560px] overflow-hidden p-0">
        <GraphCanvas
          graph={visibleGraph}
          degreeMap={visibleDegreeMap}
          style={style}
          layout={layout}
          selectedNodeIds={selectedNodeIds}
          selectedEdgeIds={selectedEdgeIds}
          highlightedNodeIds={highlightedNodeIds}
          highlightedEdgeIds={highlightedEdgeIds}
          simulationRunning={simulationRunning && !loading}
          onSimulationToggle={setSimulationRunning}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onBackgroundClick={onBackgroundClick}
          onNodeHover={onNodeHover}
          onContextAction={onContextAction}
          onVisibleBounds={onVisibleBounds}
          onUnpinAll={unpinAllNodes}
          jumpToNodeId={jumpToNodeId}
          showToolbar
        />
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[#181a1f]/80">
            <PageLoadingSpinner message="관계 그래프를 준비하는 중입니다..." />
          </div>
        ) : null}
        {selectedNode || selectedEdge || selectedNodeCount > 0 || selectedEdgeCount > 0 ? (
          <div className="absolute right-0 top-0 z-10 h-full w-80 border-l border-[#30363d] bg-[#181a1f]/95 shadow-xl">
            <div className="flex items-center justify-between border-b border-[#30363d] p-4">
              <h3 className="font-bold text-slate-100">상세 정보</h3>
              <Button variant="ghost" size="icon" onClick={onBackgroundClick} className="h-7 w-7 text-slate-400">
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-4 p-4 text-sm">
              <div className="grid grid-cols-4 gap-1">
                <Button type="button" variant="outline" size="xs" onClick={handleJumpSelected} disabled={!selectedNode}>
                  <MapPin className="h-3 w-3" />
                  이동
                </Button>
                <Button type="button" variant="outline" size="xs" onClick={handleApplyNeighborhood} disabled={!selectedNode}>
                  N-Hop
                </Button>
                <Button type="button" variant="outline" size="xs" onClick={handleHideSelected} disabled={selectedNodeCount + selectedEdgeCount === 0}>
                  숨김
                </Button>
                <Button type="button" variant="outline" size="xs" onClick={showAll}>
                  전체
                </Button>
              </div>
              <div className="rounded-md border border-[#30363d] bg-[#0d1117] p-3 text-xs text-slate-300">
                선택 노드 {formatInteger(selectedNodeCount)}개 / 선택 엣지 {formatInteger(selectedEdgeCount)}개
              </div>
              {selectedPath.length > 1 ? (
                <div className="rounded-md border border-[#30363d] bg-[#0d1117] p-3">
                  <p className="text-xs font-semibold uppercase text-slate-500">최단 경로</p>
                  <div className="mt-2 space-y-1 text-xs text-slate-200">
                    {selectedPath.map((nodeId) => (
                      <p key={nodeId} className="ontology-mono-wrap">{nodeId}</p>
                    ))}
                  </div>
                </div>
              ) : null}
              {selectedNode ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-xs font-semibold uppercase text-slate-500">{selectedNode.type}</p>
                    <input
                      aria-label="선택 노드 라벨"
                      value={selectedNode.label}
                      onChange={(event) => handleNodePatch(selectedNode.id, { label: event.target.value })}
                      className="mt-1 w-full rounded-md border border-[#30363d] bg-[#0d1117] px-2 py-1 text-base font-bold leading-snug text-slate-100"
                    />
                  </div>
                  {selectedNode.tags.length ? (
                    <div className="flex flex-wrap gap-1">
                      {selectedNode.tags.map((tag) => (
                        <span key={tag} className="rounded-full border border-sky-900/50 bg-sky-950/40 px-2 py-0.5 text-xs text-sky-200">
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => onContextAction("node", selectedNode.id, selectedNode.pinned ? "unpin" : "pin")}>
                      {selectedNode.pinned ? "핀 해제" : "핀 고정"}
                    </Button>
                    <Button type="button" variant="destructive" size="sm" onClick={() => handleDeleteSelectedNode(selectedNode.id)}>
                      노드 삭제
                    </Button>
                  </div>
                  <dl className="space-y-2 rounded-md border border-[#30363d] bg-[#0d1117] p-3">
                    {Object.entries(selectedNode.properties).map(([key, value]) => (
                      <div key={key}>
                        <dt className="text-xs text-slate-500">{key}</dt>
                        <dd className="ontology-mono-wrap mt-0.5 font-semibold text-slate-200">{String(value || "-")}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : null}
              {selectedEdge ? (
                <div className="space-y-3 rounded-md border border-[#30363d] bg-[#0d1117] p-3">
                  <div>
                    <p className="text-xs font-semibold uppercase text-slate-500">Edge</p>
                    <input
                      aria-label="선택 엣지 관계"
                      value={selectedEdge.relation}
                      onChange={(event) => handleEdgePatch(selectedEdge.id, { relation: event.target.value })}
                      className="mt-1 w-full rounded-md border border-[#30363d] bg-[#161b22] px-2 py-1 font-semibold text-slate-100"
                    />
                  </div>
                  <dl className="space-y-2">
                    <div>
                      <dt className="text-xs text-slate-500">source</dt>
                      <dd className="ontology-mono-wrap mt-0.5 font-semibold text-slate-200">{typeof selectedEdge.source === "string" ? selectedEdge.source : selectedEdge.source.id}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500">target</dt>
                      <dd className="ontology-mono-wrap mt-0.5 font-semibold text-slate-200">{typeof selectedEdge.target === "string" ? selectedEdge.target : selectedEdge.target.id}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500">weight</dt>
                      <dd className="ontology-mono-wrap mt-0.5 font-semibold text-slate-200">{selectedEdge.weight}</dd>
                    </div>
                  </dl>
                  <Button type="button" variant="destructive" size="sm" onClick={() => handleDeleteSelectedEdge(selectedEdge.id)}>
                    엣지 삭제
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
    <ActionDock
      activityActive={simulationRunning && !loading}
      activityContent={
        <JobStatusLogger
          status={`노드: ${formatInteger(visibleGraph.nodes.length)}개\n엣지: ${formatInteger(visibleGraph.edges.length)}개\n선택 노드: ${formatInteger(selectedNodeIds.size)}개`}
          isErrorStatus={false}
        />
      }
      notificationActive={false}
      notificationContent={<div className="text-sm text-slate-600 dark:text-slate-300">알림 없음</div>}
      settingsTitle="설정"
      settingsContent={
        <SettingsPanel
          style={style}
          layout={layout}
          nodeTypes={Array.from(new Set(visibleGraph.nodes.map((node) => node.type)))}
          presetNames={Object.keys(stylePresets)}
          onStyleChange={setStyle}
          onLayoutChange={updateLayout}
          onPresetChange={applyPreset}
          onPresetSave={savePreset}
        />
      }
    />
    </div>
  );
}
