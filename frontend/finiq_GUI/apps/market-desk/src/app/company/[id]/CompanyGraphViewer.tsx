"use client"

import { useMemo, useState, useEffect } from 'react'
import { GraphCanvas, SettingsPanel, useGraphViewer, DEFAULT_STYLE, DEFAULT_LAYOUT, STYLE_PRESETS } from '@finiq/graph-viewer'
import { Card, CardContent, CardHeader, CardTitle, CardDescription, Input, Button } from '@finiq/ui'
import { fetchCompanyGraphData } from './exampleGraphData'
import { PageLoadingSpinner } from '@/components/ui/PageLoadingSpinner'
import { Search, X, Save, Download, Unlock } from 'lucide-react'
import { ActionDock } from '@/components/ui/ActionDock'
import { formatInteger } from '@/lib/format'

export function CompanyGraphViewer({ companyId = 'demo' }: { companyId?: string }) {
  const [loading, setLoading] = useState(true)
  const [simulationRunning, setSimulationRunning] = useState(true)
  const [searchValue, setSearchValue] = useState('')

  // useGraphViewer hook processes GraphData and handles layout states
  const {
    graph,
    visibleGraph,
    visibleDegreeMap,
    style,
    layout,
    selectedNodeIds,
    selectedEdgeIds,
    highlightedNodeIds,
    highlightedEdgeIds,
    onNodeClick,
    onEdgeClick,
    onBackgroundClick,
    onNodeHover,
    onContextAction,
    replaceGraph,
    setSearchText,
    nodeTypes,
    filters,
    updateFilters,
    setStyle,
    updateLayout: setLayout,
    unpinAllNodes,
  } = useGraphViewer({
    initialStyle: STYLE_PRESETS['AI Studio'] ?? DEFAULT_STYLE,
    initialLayout: { ...DEFAULT_LAYOUT, chargeStrength: -400, linkDistance: 80 }
  })

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    fetchCompanyGraphData(companyId).then(data => {
      if (mounted) {
        replaceGraph(data as any);
        setLoading(false);
      }
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
    return () => { mounted = false; };
  }, [companyId, replaceGraph]);

  // Handle Search
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchValue(e.target.value);
    setSearchText(e.target.value);
  }

  // Find selected node details
  const toggleNodeTypeFilter = (type: string) => {
    const nextNodeTypes = filters.nodeTypes.includes(type)
      ? filters.nodeTypes.filter(t => t !== type)
      : [...filters.nodeTypes, type];
    updateFilters({ ...filters, nodeTypes: nextNodeTypes });
  };

  const handleSaveLayout = () => {
    const layoutState = visibleGraph.nodes.map(n => ({ id: n.id, fx: n.fx, fy: n.fy, pinned: n.pinned }));
    localStorage.setItem(`graph_layout_${companyId}`, JSON.stringify(layoutState));
    alert('레이아웃이 성공적으로 저장되었습니다.');
  };

  const handleLoadLayout = () => {
    const saved = localStorage.getItem(`graph_layout_${companyId}`);
    if (saved) {
      const layoutState = JSON.parse(saved);
      const layoutMap = new Map(layoutState.map((n: any) => [n.id, n]));
      
      const newGraph = {
        nodes: graph.nodes.map(n => {
          const savedNode: any = layoutMap.get(n.id);
          if (savedNode && savedNode.pinned) {
            return { ...n, fx: savedNode.fx, fy: savedNode.fy, pinned: true, x: savedNode.fx, y: savedNode.fy };
          }
          return n;
        }),
        edges: graph.edges
      };
      replaceGraph(newGraph as any);
    } else {
      alert('저장된 레이아웃이 없습니다.');
    }
  };
  const selectedNode = useMemo(() => {
    if (selectedNodeIds.size === 0) return null;
    const nodeId = Array.from(selectedNodeIds)[0];
    return visibleGraph.nodes.find(n => n.id === nodeId) || null;
  }, [selectedNodeIds, visibleGraph.nodes]);

  if (loading) {
    return (
      <Card className="dark:bg-[#161b22] dark:border-[#30363d] flex flex-col h-[700px] items-center justify-center">
        <PageLoadingSpinner message="관계망 데이터를 분석 중입니다..." />
      </Card>
    )
  }

  return (
    <div className="relative flex h-[700px] flex-col gap-4">
      <Card className="flex-1 dark:bg-[#161b22] dark:border-[#30363d] flex flex-col h-full">
        <CardHeader className="flex flex-row items-center justify-between pb-2 border-b dark:border-[#30363d]">
        <div>
          <CardTitle className="text-lg dark:text-white">Graph View</CardTitle>
          <CardDescription className="dark:text-slate-400">
            기업의 지배구조, 주요 안건 결의 행위, 증권 발행 내역 등을 시각화합니다.
          </CardDescription>
        </div>
        
        {/* Toolbar Section */}
        <div className="flex flex-col md:flex-row items-center gap-2">
          {nodeTypes.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 bg-slate-50 dark:bg-[#0d1117] p-1 rounded-md border dark:border-[#30363d]">
              {nodeTypes.map(type => {
                const isActive = filters.nodeTypes.length === 0 || filters.nodeTypes.includes(type);
                return (
                  <Button
                    key={type}
                    variant={isActive ? "default" : "outline"}
                    size="xs"
                    onClick={() => toggleNodeTypeFilter(type)}
                    className={`h-6 text-[10px] px-2 ${isActive ? 'bg-blue-600 text-white' : 'dark:text-slate-400 dark:border-[#30363d]'}`}
                  >
                    {type}
                  </Button>
                )
              })}
            </div>
          )}
          <div className="relative">
            <Search className="absolute left-2.5 top-1.5 h-4 w-4 text-slate-500" />
            <Input 
              type="text" 
              placeholder="노드 검색..." 
              value={searchValue}
              onChange={handleSearchChange}
              className="pl-9 w-64 h-8 text-sm bg-slate-50 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-white"
            />
          </div>
          <div className="flex items-center gap-1 bg-slate-50 dark:bg-[#0d1117] p-1 rounded-md border dark:border-[#30363d]">
            <Button variant="ghost" size="icon" onClick={() => unpinAllNodes()} title="모든 핀 해제" className="h-6 w-6">
              <Unlock className="h-4 w-4 text-slate-500 hover:text-blue-600" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleSaveLayout} title="현재 레이아웃 저장" className="h-6 w-6">
              <Save className="h-4 w-4 text-slate-500 hover:text-blue-600" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleLoadLayout} title="저장된 레이아웃 불러오기" className="h-6 w-6">
              <Download className="h-4 w-4 text-slate-500 hover:text-blue-600" />
            </Button>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="flex-1 p-0 overflow-hidden relative flex flex-row">
        {/* Main Graph Area */}
        <div className="flex-1 relative h-full">
          <GraphCanvas
            graph={visibleGraph}
            degreeMap={visibleDegreeMap}
            style={style}
            layout={layout}
            selectedNodeIds={selectedNodeIds}
            selectedEdgeIds={selectedEdgeIds}
            highlightedNodeIds={highlightedNodeIds}
            highlightedEdgeIds={highlightedEdgeIds}
            simulationRunning={simulationRunning}
            onSimulationToggle={setSimulationRunning}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onBackgroundClick={onBackgroundClick}
            onNodeHover={onNodeHover}
            onContextAction={onContextAction}
            onUnpinAll={unpinAllNodes}
            onVisibleBounds={() => {}}
            showToolbar={true} // Internal canvas toolbar
          />
        </div>

        {/* Side Panel for Node Details */}
        {selectedNode && (
          <div className="w-80 h-full border-l dark:border-[#30363d] bg-white dark:bg-[#161b22] flex flex-col absolute right-0 top-0 z-10 shadow-xl transition-transform transform translate-x-0">
            <div className="flex items-center justify-between p-4 border-b dark:border-[#30363d]">
              <h3 className="font-bold text-slate-900 dark:text-white">상세 정보</h3>
              <Button variant="ghost" size="icon" onClick={onBackgroundClick} className="h-6 w-6">
                <X className="h-4 w-4 text-slate-500" />
              </Button>
            </div>
            <div className="flex-1 p-4 overflow-y-auto">
              <div className="flex flex-col gap-4">
                <div>
                  <span className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase">{selectedNode.type}</span>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 leading-tight mt-1">{selectedNode.label}</h2>
                </div>

                {selectedNode.tags && selectedNode.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {selectedNode.tags.map(tag => (
                      <span key={tag} className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-900/50">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {selectedNode.properties && Object.keys(selectedNode.properties).length > 0 && (
                  <div className="bg-slate-50 dark:bg-[#0d1117] rounded-md border dark:border-[#30363d] p-3 text-sm">
                    <h4 className="font-semibold text-slate-700 dark:text-slate-300 mb-2 border-b dark:border-[#30363d] pb-2">속성 (Properties)</h4>
                    <dl className="grid grid-cols-1 gap-2">
                      {Object.entries(selectedNode.properties).map(([key, value]) => (
                        <div key={key} className="flex flex-col">
                          <dt className="text-xs text-slate-500 dark:text-slate-400 font-medium">{key}</dt>
                          <dd className="text-sm font-semibold text-slate-900 dark:text-slate-200 mt-0.5 whitespace-pre-wrap">
                            {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </CardContent>
      </Card>
      <ActionDock
        activityTitle="그래프 현황"
        activityActive={simulationRunning}
        activityContent={<div className="text-sm dark:text-slate-300">노드 {formatInteger(visibleGraph.nodes.length)}개, 엣지 {formatInteger(visibleGraph.edges.length)}개</div>}
        notificationActive={selectedNodeIds.size > 0}
        notificationContent={<div className="text-sm dark:text-slate-300">{selectedNodeIds.size ? `선택 노드 ${formatInteger(selectedNodeIds.size)}개` : "알림 없음"}</div>}
        settingsTitle="시스템 설정"
        settingsContent={
          <SettingsPanel
            style={style}
            layout={layout}
            nodeTypes={Array.from(new Set(visibleGraph.nodes.map(n => n.type)))}
            presetNames={Object.keys(STYLE_PRESETS)}
            onStyleChange={setStyle}
            onLayoutChange={setLayout}
            onPresetChange={(presetName) => {
              const preset = STYLE_PRESETS[presetName]
              if (preset) setStyle(preset)
            }}
            onPresetSave={() => {}}
          />
        }
      />
    </div>
  )
}
