import type { GraphData } from '../types/graph'
import { ConnectionConfig } from './ConnectionConfig'
import { EntityNodeForm } from './EntityNodeForm'
import { RelationshipEdgeForm } from './RelationshipEdgeForm'
import { CypherConsole } from './CypherConsole'

interface DatabasePanelProps {
  graph: GraphData
  onRefreshGraph: () => void
  onCypherResult: (customGraph: GraphData) => void
}

export function DatabasePanel(props: DatabasePanelProps) {
  const { graph, onRefreshGraph, onCypherResult } = props

  return (
    <div className="flex flex-col gap-6 h-full overflow-y-auto p-4 bg-background/40 backdrop-blur-sm text-foreground">
      <ConnectionConfig onRefreshGraph={onRefreshGraph} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <EntityNodeForm onRefreshGraph={onRefreshGraph} />
        <RelationshipEdgeForm graph={graph} onRefreshGraph={onRefreshGraph} />
      </div>

      <CypherConsole onCypherResult={onCypherResult} />
    </div>
  )
}
