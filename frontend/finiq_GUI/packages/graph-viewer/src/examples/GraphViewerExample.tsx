import { useState, useEffect, useCallback } from 'react'
import { LeftPanel } from '../components/LeftPanel'
import { RightPanel } from '../components/RightPanel'
import { SettingsPanel } from '../components/SettingsPanel'
import { SPLCView } from '../components/SPLCView'
import { RMAPView } from '../components/RMAPView'
import { KOGridView } from '../components/KOGridView'
import { DatabasePanel } from '../components/DatabasePanel'
import { apiClient } from '../utils/apiClient'
import { GraphCanvas, useGraphViewer, shortestPath } from '../index'
import type { GraphData } from '../types/graph'
import { Button, Card } from '@finiq/ui'
import { Undo2, Redo2, Sun, Moon, Network, Database, Layers, GitBranch, ShieldAlert } from 'lucide-react'

export function GraphViewerExample() {
  const viewer = useGraphViewer()
  const [activeTab, setActiveTab] = useState<'network' | 'splc' | 'rmap' | 'kogrid' | 'database'>('network')
  const [focusEntityId, setFocusEntityId] = useState<string>('samsung-elec')
  const [dbMode, setDbMode] = useState<'api' | 'fallback'>(apiClient.getMode())

  // Force a graph load (from fallback or backend API)
  const refreshGraphData = useCallback(async () => {
    try {
      const dbGraph = await apiClient.fetchGraph()
      viewer.replaceGraph(dbGraph)
      setDbMode(apiClient.getMode())
    } catch (e) {
      console.error('Failed to sync graph with database service:', e)
    }
  }, [viewer.replaceGraph])

  useEffect(() => {
    refreshGraphData()
  }, [])

  // Sync selection from Force Graph to focusEntityId
  const selectedNode = viewer.graph.nodes.find((n) => viewer.selectedNodeIds.has(n.id))
  const selectedEdge = viewer.graph.edges.find((e) => viewer.selectedEdgeIds.has(e.id))

  useEffect(() => {
    if (selectedNode) {
      setFocusEntityId(selectedNode.id)
    }
  }, [selectedNode])

  // Drilldown function used in SPLC, RMAP, KOgrid subviews
  const handleSetFocusEntity = useCallback((id: string) => {
    setFocusEntityId(id)
    // Select the node in the viewer state as well so switching back to Graph displays it
    viewer.onNodeClick({ id } as any, false)
  }, [viewer.onNodeClick])

  // Custom Cypher query handler
  const handleCypherResult = useCallback((customGraph: GraphData) => {
    viewer.replaceGraph(customGraph)
  }, [viewer.replaceGraph])

  // Raw Graph data updates from simulator
  const handleGraphUpdate = useCallback((updatedGraph: GraphData) => {
    viewer.replaceGraph(updatedGraph)
  }, [viewer.replaceGraph])

  return (
    <div className="flex flex-col h-screen bg-background text-foreground overflow-hidden font-sans">
      {/* Header */}
      <header className="flex flex-col md:flex-row items-center justify-between px-6 py-3 border-b bg-card gap-4 shrink-0 shadow-sm z-20">
        <div className="flex items-center gap-4 w-full md:w-auto">
          <div className="flex flex-col">
            <span className="text-[10px] font-bold text-primary uppercase tracking-[0.2em] flex items-center gap-1">
              <Network className="w-3.5 h-3.5 text-primary" /> FINIQ Entity Studio
            </span>
            <h1 className="text-base font-extrabold tracking-tight">Systemic Relationship Visualizer</h1>
          </div>

          {/* Database Mode Badge */}
          <div className="ml-2">
            {dbMode === 'api' ? (
              <span className="text-[10px] bg-green-500/10 text-green-500 border border-green-500/30 px-2 py-0.5 rounded-full font-bold flex items-center gap-1 select-none">
                <Database className="w-3 h-3" /> API Live
              </span>
            ) : (
              <span className="text-[10px] bg-yellow-500/10 text-yellow-500 border border-yellow-500/30 px-2 py-0.5 rounded-full font-bold flex items-center gap-1 select-none">
                <Database className="w-3 h-3" /> Local Mode
              </span>
            )}
          </div>
        </div>

        {/* View Mode Switching Tabs (Bloomberg Inspired Segmented Controls) */}
        <div className="flex bg-muted rounded-xl p-1 text-xs font-bold border max-w-full overflow-x-auto">
          <button
            onClick={() => setActiveTab('network')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg transition-colors whitespace-nowrap ${activeTab === 'network' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
          >
            <Network className="w-3.5 h-3.5" /> Graph Explorer
          </button>
          <button
            onClick={() => setActiveTab('splc')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg transition-colors whitespace-nowrap ${activeTab === 'splc' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
          >
            <Layers className="w-3.5 h-3.5" /> SPLC Supply Chain
          </button>
          <button
            onClick={() => setActiveTab('rmap')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg transition-colors whitespace-nowrap ${activeTab === 'rmap' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
          >
            <GitBranch className="w-3.5 h-3.5" /> RMAP Hierarchy
          </button>
          <button
            onClick={() => setActiveTab('kogrid')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg transition-colors whitespace-nowrap ${activeTab === 'kogrid' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
          >
            <ShieldAlert className="w-3.5 h-3.5" /> KOgrid Risk Simulator
          </button>
          <button
            onClick={() => setActiveTab('database')}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg transition-colors whitespace-nowrap ${activeTab === 'database' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
          >
            <Database className="w-3.5 h-3.5" /> DB Manager
          </button>
        </div>

        {/* Global Controls */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center bg-muted rounded-lg p-1">
            <Button variant="ghost" size="icon-xs" onClick={viewer.undo} disabled={!viewer.canUndo}>
              <Undo2 className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="icon-xs" onClick={viewer.redo} disabled={!viewer.canRedo}>
              <Redo2 className="w-4 h-4" />
            </Button>
          </div>

          <Button variant="outline" size="sm" onClick={viewer.toggleTheme} className="gap-2 h-8">
            {viewer.appTheme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            <span className="text-xs uppercase font-bold">{viewer.appTheme === 'light' ? 'Dark' : 'Light'}</span>
          </Button>
        </div>
      </header>

      {/* Main Workspace Display Content */}
      <main className="flex-1 flex overflow-hidden p-3 gap-3 bg-muted/30 relative">
        {activeTab === 'network' ? (
          <>
            {/* Standard Network Workspace Layout */}
            <aside className="w-72 shrink-0 flex flex-col">
              <LeftPanel
                searchText={viewer.searchText}
                onSearchTextChange={viewer.setSearchText}
                filters={viewer.filters}
                onFiltersChange={viewer.updateFilters}
                graph={viewer.graph}
                runCorporateAnalysis={viewer.runCorporateAnalysis}
              />
            </aside>

            <div className="flex-1 flex flex-col min-w-0 gap-3">
              <Card className="flex-1 relative overflow-hidden bg-card/50 backdrop-blur-sm border-2">
                {viewer.visibleGraph.nodes.length === 0 ? (
                  <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                    <p>No visible data. Try seeding defaults or adding new nodes in DB Manager.</p>
                  </div>
                ) : (
                  <GraphCanvas
                    graph={viewer.visibleGraph}
                    degreeMap={viewer.visibleDegreeMap}
                    style={viewer.style}
                    layout={viewer.layout}
                    selectedNodeIds={viewer.selectedNodeIds}
                    selectedEdgeIds={viewer.selectedEdgeIds}
                    highlightedNodeIds={viewer.highlightedNodeIds}
                    highlightedEdgeIds={viewer.highlightedEdgeIds}
                    simulationRunning={viewer.simulationRunning}
                    onSimulationToggle={viewer.setSimulationRunning}
                    onNodeClick={viewer.onNodeClick}
                    onEdgeClick={viewer.onEdgeClick}
                    onBackgroundClick={viewer.onBackgroundClick}
                    onNodeHover={viewer.onNodeHover}
                    onContextAction={viewer.onContextAction}
                    onVisibleBounds={viewer.onVisibleBounds}
                    onUnpinAll={viewer.unpinAllNodes}
                    jumpToNodeId={undefined}
                    showToolbar={true}
                  />
                )}
              </Card>

              {/* Bottom: Settings */}
              <div className="h-48 shrink-0 overflow-hidden">
                <SettingsPanel
                  style={viewer.style}
                  layout={viewer.layout}
                  nodeTypes={viewer.nodeTypes}
                  presetNames={Object.keys(viewer.stylePresets)}
                  onStyleChange={viewer.setStyle}
                  onLayoutChange={viewer.updateLayout}
                  onPresetChange={viewer.applyPreset}
                  onPresetSave={viewer.savePreset}
                />
              </div>
            </div>

            <aside className="w-80 shrink-0">
              <RightPanel
                graph={viewer.graph}
                selectedNode={selectedNode}
                selectedEdge={selectedEdge}
                selectedNodeIds={viewer.selectedNodeIds}
                selectedEdgeIds={viewer.selectedEdgeIds}
                visitHistory={[]}
                shortestPath={
                  viewer.selectedNodeIds.size === 2
                    ? shortestPath(viewer.graph, Array.from(viewer.selectedNodeIds)[0], Array.from(viewer.selectedNodeIds)[1])
                    : []
                }
                onNodePatch={(id, patch) =>
                  viewer.setGraph((curr) => ({
                    nodes: curr.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
                    edges: curr.edges,
                  }))
                }
                onEdgePatch={(id, patch) =>
                  viewer.setGraph((curr) => ({
                    nodes: curr.nodes,
                    edges: curr.edges.map((e) => (e.id === id ? { ...e, ...patch } : e)),
                  }))
                }
                onDeleteNode={async (id) => {
                  try {
                    await apiClient.deleteNode(id)
                    refreshGraphData()
                  } catch (e: any) {
                    alert(`Failed to delete node from DB: ${e.message}`)
                  }
                }}
                onDeleteEdge={async (id) => {
                  try {
                    await apiClient.deleteEdge(id)
                    refreshGraphData()
                  } catch (e: any) {
                    alert(`Failed to delete edge from DB: ${e.message}`)
                  }
                }}
                onPinNode={(id, pin) => viewer.onContextAction('node', id, pin ? 'pin' : 'unpin')}
                onHideSelected={() => {}}
                onShowHidden={() => {}}
                onApplyNeighborhood={() => {}}
                onJumpSelected={() => {}}
              />
            </aside>
          </>
        ) : activeTab === 'splc' ? (
          <div className="flex-1 h-full overflow-hidden">
            <SPLCView
              graph={viewer.graph}
              focusEntityId={focusEntityId}
              onSetFocusEntity={handleSetFocusEntity}
            />
          </div>
        ) : activeTab === 'rmap' ? (
          <div className="flex-1 h-full overflow-hidden">
            <RMAPView
              graph={viewer.graph}
              focusEntityId={focusEntityId}
              onSetFocusEntity={handleSetFocusEntity}
            />
          </div>
        ) : activeTab === 'kogrid' ? (
          <div className="flex-1 h-full overflow-hidden">
            <KOGridView
              graph={viewer.graph}
              focusEntityId={focusEntityId}
              onSetFocusEntity={handleSetFocusEntity}
              onGraphUpdate={handleGraphUpdate}
            />
          </div>
        ) : (
          <div className="flex-1 h-full overflow-hidden">
            <DatabasePanel
              graph={viewer.graph}
              onRefreshGraph={refreshGraphData}
              onCypherResult={handleCypherResult}
            />
          </div>
        )}
      </main>

      {/* Footer / Status Bar */}
      <footer className="h-8 border-t bg-card flex items-center px-4 justify-between shrink-0 text-xs shadow-inner">
        <div className="flex items-center gap-4 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            Query Engine Active
          </div>
          <div>Nodes Count: {viewer.graph.nodes.length}</div>
          <div>Edges Count: {viewer.graph.edges.length}</div>
          <div>Active Focus: <span className="text-primary font-bold">{focusEntityId}</span></div>
        </div>

        {viewer.performanceWarning && (
          <div className="text-[10px] text-amber-500 font-bold flex items-center gap-1.5">
            Performance Warning: High Node Capacity Detected
          </div>
        )}
      </footer>
    </div>
  )
}
