import { LeftPanel } from '../components/LeftPanel'
import { SettingsPanel } from '../components/SettingsPanel'
import { GraphCanvas, useGraphViewer } from '../index'
import { AppHeader, EmptyState } from '@finiq/ui'

export function GraphViewerExample() {
  const viewer = useGraphViewer()

  const renderGraphCanvas = () =>
    viewer.visibleGraph.nodes.length === 0 ? (
      <EmptyState title="No visible graph">
        Choose a JSON file, clear filters, or show hidden nodes to render the graph.
      </EmptyState>
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
      />
    )

  return (
    <div className="app" data-theme={viewer.appTheme}>
      <AppHeader
        kicker="FINIQ Graph Studio"
        title="Entity Graph Viewer"
        description="Explore relationship graphs and tune their visual layout in one focused workspace."
        actions={
          <>
          <button
            type="button"
            className="theme-toggle"
            onClick={viewer.toggleTheme}
            aria-pressed={viewer.appTheme === 'light'}
          >
            {viewer.appTheme === 'light' ? 'Light' : 'Dark'}
          </button>
          <button type="button" onClick={viewer.undo} disabled={!viewer.canUndo}>Undo</button>
          <button type="button" onClick={viewer.redo} disabled={!viewer.canRedo}>Redo</button>
          </>
        }
      />

      {viewer.performanceWarning ? (
        <div className="performance-warning">
          Performance warning: large graph detected ({viewer.graph.nodes.length} nodes / {viewer.graph.edges.length} edges). Labels are progressively rendered and controls are debounced for smoother interaction.
        </div>
      ) : null}

      <main className="layout graph-page">
        <aside className="workspace-column">
          <LeftPanel
            searchText={viewer.searchText}
            onSearchTextChange={viewer.setSearchText}
            filters={viewer.filters}
            onFiltersChange={viewer.updateFilters}
            graph={viewer.graph}
          />
        </aside>
        <section className="center-column">{renderGraphCanvas()}</section>
        <section className="graph-data-row" aria-label="Data file">
          <h2>Data</h2>
          <label className="file-upload">
            Choose File
            <input
              type="file"
              accept=".json,application/json"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  void viewer.importFromFile(file)
                }
              }}
            />
          </label>
          <textarea
            className="json-editor inline"
            value={viewer.importText}
            rows={6}
            readOnly
            spellCheck={false}
            placeholder="Choose a JSON file to preview its contents."
          />
        </section>
        <section className="graph-style-row" aria-label="Style settings">
          <SettingsPanel
            style={viewer.style}
            layout={viewer.layout}
            nodeTypes={viewer.nodeTypes}
            presetNames={Object.keys(viewer.stylePresets)}
            onStyleChange={viewer.setStyle}
            onLayoutChange={viewer.updateLayout}
            onPresetChange={viewer.applyPreset}
            onPresetAdd={viewer.addPreset}
            onPresetRemove={viewer.removePreset}
            onPresetSave={viewer.savePreset}
          />
        </section>
      </main>
    </div>
  )
}
