import type { GraphData, GraphEdge, GraphNode } from '../types/graph'

interface RightPanelProps {
  graph: GraphData
  selectedNode: GraphNode | undefined
  selectedEdge: GraphEdge | undefined
  selectedNodeIds: Set<string>
  selectedEdgeIds: Set<string>
  visitHistory: string[]
  shortestPath: string[]
  onNodePatch: (nodeId: string, patch: Partial<GraphNode>) => void
  onEdgePatch: (edgeId: string, patch: Partial<GraphEdge>) => void
  onDeleteNode: (nodeId: string) => void
  onDeleteEdge: (edgeId: string) => void
  onPinNode: (nodeId: string, pinned: boolean) => void
  onHideSelected: () => void
  onShowHidden: () => void
  onApplyNeighborhood: () => void
  onJumpSelected: () => void
}

function parsePropertiesJson(input: string): Record<string, unknown> | null {
  if (!input.trim()) {
    return {}
  }
  try {
    const parsed = JSON.parse(input)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return null
    }
    return parsed as Record<string, unknown>
  } catch {
    return null
  }
}

export function RightPanel(props: RightPanelProps) {
  const {
    selectedNode,
    selectedEdge,
    selectedNodeIds,
    selectedEdgeIds,
    visitHistory,
    shortestPath,
    onNodePatch,
    onEdgePatch,
    onDeleteNode,
    onDeleteEdge,
    onPinNode,
    onHideSelected,
    onShowHidden,
    onApplyNeighborhood,
    onJumpSelected,
  } = props

  return (
    <div className="side-panel right-panel">
      <section>
        <h2>Selection</h2>
        <p>{selectedNodeIds.size} node(s), {selectedEdgeIds.size} edge(s)</p>
        <div className="stack">
          <button type="button" onClick={onJumpSelected}>Jump to selected</button>
          <button type="button" onClick={onApplyNeighborhood}>Show N-hop neighborhood</button>
          <button type="button" onClick={onHideSelected}>Hide selected</button>
          <button type="button" onClick={onShowHidden}>Show all hidden</button>
        </div>
      </section>

      <section>
        <h2>Node details</h2>
        {!selectedNode ? (
          <p className="empty">Select a node to inspect or edit.</p>
        ) : (
          <div className="stack">
            <label>
              ID
              <input value={selectedNode.id} disabled />
            </label>
            <label>
              Label
              <input
                value={selectedNode.label}
                onChange={(event) => onNodePatch(selectedNode.id, { label: event.target.value })}
              />
            </label>
            <label>
              Type
              <input
                value={selectedNode.type}
                onChange={(event) => onNodePatch(selectedNode.id, { type: event.target.value || 'default' })}
              />
            </label>
            <label>
              Group
              <input
                value={selectedNode.group ?? ''}
                onChange={(event) => onNodePatch(selectedNode.id, { group: event.target.value || undefined })}
              />
            </label>
            <label>
              Tags (comma separated)
              <input
                value={selectedNode.tags.join(', ')}
                onChange={(event) =>
                  onNodePatch(selectedNode.id, {
                    tags: event.target.value.split(',').map((v) => v.trim()).filter(Boolean),
                  })
                }
              />
            </label>
            <label>
              Properties (JSON object)
              <textarea
                rows={5}
                value={JSON.stringify(selectedNode.properties, null, 2)}
                onChange={(event) => {
                  const parsed = parsePropertiesJson(event.target.value)
                  if (parsed) {
                    onNodePatch(selectedNode.id, { properties: parsed })
                  }
                }}
              />
            </label>
            <div className="split-row">
              <button type="button" onClick={() => onPinNode(selectedNode.id, !selectedNode.pinned)}>
                {selectedNode.pinned ? 'Unpin node' : 'Pin node'}
              </button>
              <button type="button" className="danger" onClick={() => onDeleteNode(selectedNode.id)}>
                Delete node
              </button>
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>Edge details</h2>
        {!selectedEdge ? (
          <p className="empty">Select an edge to inspect or edit.</p>
        ) : (
          <div className="stack">
            <label>
              ID
              <input value={selectedEdge.id} disabled />
            </label>
            <label>
              Relation
              <input
                value={selectedEdge.relation}
                onChange={(event) => onEdgePatch(selectedEdge.id, { relation: event.target.value || 'related' })}
              />
            </label>
            <label>
              Weight
              <input
                type="number"
                step={0.1}
                value={selectedEdge.weight}
                onChange={(event) => onEdgePatch(selectedEdge.id, { weight: Math.max(0.1, Number(event.target.value) || 1) })}
              />
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={selectedEdge.directed}
                onChange={(event) => onEdgePatch(selectedEdge.id, { directed: event.target.checked })}
              />
              Directed edge
            </label>
            <label>
              Properties (JSON object)
              <textarea
                rows={4}
                value={JSON.stringify(selectedEdge.properties, null, 2)}
                onChange={(event) => {
                  const parsed = parsePropertiesJson(event.target.value)
                  if (parsed) {
                    onEdgePatch(selectedEdge.id, { properties: parsed })
                  }
                }}
              />
            </label>
            <button type="button" className="danger" onClick={() => onDeleteEdge(selectedEdge.id)}>
              Delete edge
            </button>
          </div>
        )}
      </section>

      <section>
        <h2>Navigation history</h2>
        {visitHistory.length === 0 ? <p className="empty">No visited nodes yet.</p> : null}
        <div className="history-list">
          {visitHistory.map((id, idx) => (
            <code key={`${id}-${idx}`}>{id}</code>
          ))}
        </div>
      </section>

      <section>
        <h2>Shortest path</h2>
        {shortestPath.length <= 1 ? (
          <p className="empty">Select two nodes to compute shortest path.</p>
        ) : (
          <p>{shortestPath.join(' → ')}</p>
        )}
      </section>
    </div>
  )
}
