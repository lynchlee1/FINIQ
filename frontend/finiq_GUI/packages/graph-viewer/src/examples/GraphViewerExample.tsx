import { LeftPanel } from '../components/LeftPanel'
import { RightPanel } from '../components/RightPanel'
import { SettingsPanel } from '../components/SettingsPanel'
import { GraphCanvas, useGraphViewer } from '../index'
import { Button, Card } from '@finiq/ui'
import { Undo2, Redo2, Sun, Moon } from 'lucide-react'

export function GraphViewerExample() {
  const viewer = useGraphViewer()

  const selectedNode = viewer.graph.nodes.find(n => viewer.selectedNodeIds.has(n.id))
  const selectedEdge = viewer.graph.edges.find(e => viewer.selectedEdgeIds.has(e.id))

  return (
    <div className="flex flex-col h-screen bg-background text-foreground overflow-hidden font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b bg-card shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <span className="text-[10px] font-bold text-primary uppercase tracking-[0.2em]">FINIQ Graph Studio</span>
            <h1 className="text-lg font-bold tracking-tight">Entity Analysis Dashboard</h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-muted rounded-lg p-1 mr-2">
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

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden p-3 gap-3 bg-muted/30">
        {/* Left Sidebar */}
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

        {/* Center: Graph Canvas */}
        <div className="flex-1 flex flex-col min-w-0 gap-3">
          <Card className="flex-1 relative overflow-hidden bg-card/50 backdrop-blur-sm border-2">
            {viewer.visibleGraph.nodes.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                <p>No visible data. Try clearing filters or importing a JSON file.</p>
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
                jumpToNodeId={undefined}
                showToolbar={true}
              />
            )}
          </Card>

          {/* Bottom: Settings (Collapsible or fixed) */}
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

        {/* Right Sidebar */}
        <aside className="w-80 shrink-0">
          <RightPanel
            graph={viewer.graph}
            selectedNode={selectedNode}
            selectedEdge={selectedEdge}
            selectedNodeIds={viewer.selectedNodeIds}
            selectedEdgeIds={viewer.selectedEdgeIds}
            visitHistory={[]} // Connect actual history if available
            shortestPath={[]} // Connect actual path if available
            onNodePatch={(id, patch) => viewer.setGraph(curr => ({
              nodes: curr.nodes.map(n => n.id === id ? { ...n, ...patch } : n),
              edges: curr.edges
            }))}
            onEdgePatch={(id, patch) => viewer.setGraph(curr => ({
              nodes: curr.nodes,
              edges: curr.edges.map(e => e.id === id ? { ...e, ...patch } : e)
            }))}
            onDeleteNode={(id) => viewer.onContextAction('node', id, 'delete')}
            onDeleteEdge={(id) => viewer.onContextAction('edge', id, 'delete')}
            onPinNode={(id, pin) => viewer.onContextAction('node', id, pin ? 'pin' : 'unpin')}
            onHideSelected={() => {}} // Connect actual actions
            onShowHidden={() => {}}
            onApplyNeighborhood={() => {}}
            onJumpSelected={() => {}}
          />
        </aside>
      </main>

      {/* Footer / Status Bar */}
      <footer className="h-8 border-t bg-card flex items-center px-4 justify-between shrink-0">
        <div className="flex items-center gap-4 text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            Engine Active
          </div>
          <div>Nodes: {viewer.graph.nodes.length}</div>
          <div>Edges: {viewer.graph.edges.length}</div>
        </div>
        
        {viewer.performanceWarning && (
          <div className="text-[10px] text-amber-500 font-bold flex items-center gap-1.5">
             Performance Warning: Large Dataset
          </div>
        )}
      </footer>
    </div>
  )
}
