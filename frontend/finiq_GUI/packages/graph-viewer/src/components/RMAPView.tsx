import { useMemo, useState } from 'react'
import type { GraphData, GraphNode, GraphEdge } from '../types/graph'
import { Card, CardContent, CardHeader, CardTitle, Button } from '@finiq/ui'
import { ChevronDown, ChevronRight, GitFork, Network, UserCheck, Users, Percent, ShieldCheck } from 'lucide-react'

interface RMAPViewProps {
  graph: GraphData
  focusEntityId: string
  onSetFocusEntity: (id: string) => void
}

export function RMAPView(props: RMAPViewProps) {
  const { graph, focusEntityId, onSetFocusEntity } = props
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    shareholders: true,
    subsidiaries: true,
    management: true,
  })

  // Resolve focus node
  const focusNode = useMemo(
    () => graph.nodes.find((n) => n.id === focusEntityId) || graph.nodes[0],
    [graph.nodes, focusEntityId]
  )

  const focusId = focusNode?.id || ''

  const toId = (val: string | GraphNode): string => (typeof val === 'string' ? val : val.id)

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }))
  }

  // --- Board & Executives ---
  const executives = useMemo(() => {
    return graph.edges
      .filter((e) => toId(e.target) === focusId && e.category === 'personnel')
      .map((e) => {
        const exec = graph.nodes.find((n) => n.id === toId(e.source))
        return exec ? { node: exec, edge: e } : null
      })
      .filter(Boolean) as { node: GraphNode; edge: GraphEdge }[]
  }, [graph.edges, graph.nodes, focusId])

  // Recursively fetch shareholders (for nested visual support)
  const getNestedShareholders = (nodeId: string, depth = 0): any[] => {
    if (depth > 2) return [] // Prevent infinite cycles
    return graph.edges
      .filter((e) => toId(e.target) === nodeId && e.category === 'equity')
      .map((e) => {
        const owner = graph.nodes.find((n) => n.id === toId(e.source))
        if (!owner) return null
        return {
          node: owner,
          edge: e,
          nested: getNestedShareholders(owner.id, depth + 1),
        }
      })
      .filter(Boolean) as any[]
  }

  // Recursively fetch subsidiaries
  const getNestedSubsidiaries = (nodeId: string, depth = 0): any[] => {
    if (depth > 2) return []
    return graph.edges
      .filter((e) => toId(e.source) === nodeId && e.category === 'equity')
      .map((e) => {
        const sub = graph.nodes.find((n) => n.id === toId(e.target))
        if (!sub) return null
        return {
          node: sub,
          edge: e,
          nested: getNestedSubsidiaries(sub.id, depth + 1),
        }
      })
      .filter(Boolean) as any[]
  }

  const nestedShareholders = useMemo(() => getNestedShareholders(focusId), [graph, focusId])
  const nestedSubsidiaries = useMemo(() => getNestedSubsidiaries(focusId), [graph, focusId])

  if (!focusNode) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Select a corporate entity to inspect relationship maps (RMAP).
      </div>
    )
  }

  // Recursive Tree Node Renderer
  const renderTreeNode = (item: any, type: 'up' | 'down', depth = 0) => {
    const { node, edge, nested } = item
    const isExpandable = nested && nested.length > 0
    const [isLocalExpanded, setIsLocalExpanded] = useState(true)

    return (
      <div key={`${node.id}-${depth}`} className="pl-4 border-l border-muted-foreground/20 mt-2">
        <div className="flex items-center justify-between p-2 rounded-lg bg-card/40 hover:bg-muted/40 transition-colors border group relative">
          <div className="flex items-center gap-2 min-w-0">
            {isExpandable ? (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setIsLocalExpanded(!isLocalExpanded)
                }}
                className="p-0.5 rounded hover:bg-muted shrink-0 text-muted-foreground"
              >
                {isLocalExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            ) : (
              <div className="w-4 h-4 shrink-0 flex items-center justify-center text-muted-foreground/30">
                •
              </div>
            )}
            <span
              onClick={() => onSetFocusEntity(node.id)}
              className="font-bold text-xs truncate cursor-pointer hover:underline hover:text-primary"
            >
              {node.label}
            </span>
            <span className="text-[10px] text-muted-foreground bg-muted/60 px-1 rounded-sm">
              {node.type}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[11px] font-black text-primary flex items-center gap-0.5">
              <Percent className="w-3 h-3 text-muted-foreground" /> {edge.weight || '0.01'}%
            </span>
            <Button
              variant="ghost"
              size="xs"
              className="h-5 px-1.5 text-[9px] opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={() => onSetFocusEntity(node.id)}
            >
              Focus
            </Button>
          </div>
        </div>

        {isExpandable && isLocalExpanded && (
          <div className="ml-2 flex flex-col gap-1">
            {nested.map((child: any) => renderTreeNode(child, type, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 h-full overflow-y-auto p-4 bg-background/40 backdrop-blur-sm text-foreground">
      {/* RMAP Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 border rounded-xl bg-card/60">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Network className="w-5 h-5 text-primary animate-pulse" />
            Bloomberg RMAP: Corporate Governance Registry
          </h2>
          <p className="text-xs text-muted-foreground">
            Displaying structural control linkages, voting rights ownership, and cross-affiliate management boards.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-muted/50 border rounded-lg p-1.5 text-xs font-semibold select-none">
          <ShieldCheck className="w-4 h-4 text-green-500" />
          <span>Active Entity: {focusNode.label}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Upstream Structure (Ownership & Shareholdings) */}
        <Card className="bg-card/30 flex flex-col">
          <CardHeader
            onClick={() => toggleSection('shareholders')}
            className="p-4 pb-2 border-b cursor-pointer flex flex-row items-center justify-between bg-card/30"
          >
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Users className="w-4 h-4 text-blue-400" />
              Upstream Shareholders (Control Tree)
            </CardTitle>
            <span className="text-xs text-muted-foreground">
              {expandedSections.shareholders ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </span>
          </CardHeader>
          {expandedSections.shareholders && (
            <CardContent className="p-3 flex-1">
              {nestedShareholders.length === 0 ? (
                <div className="p-8 border border-dashed rounded-lg text-center text-xs text-muted-foreground">
                  No upstream equity mapped.
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  {nestedShareholders.map((item) => renderTreeNode(item, 'up'))}
                </div>
              )}
            </CardContent>
          )}
        </Card>

        {/* Focus Node Profile */}
        <Card className="bg-card/40 border-primary/20 shadow-xl flex flex-col self-start">
          <CardHeader className="p-4 pb-2 border-b bg-primary/5">
            <CardTitle className="text-xs font-bold uppercase tracking-widest text-primary flex items-center gap-1.5">
              <GitFork className="w-4 h-4" /> Active Entity Focus Profile
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            <div>
              <h3 className="text-base font-extrabold text-foreground">{focusNode.label}</h3>
              <p className="text-xs text-muted-foreground">{focusNode.properties.sector as string || 'General Sector'}</p>
            </div>

            <div className="space-y-2 border-t pt-3 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Group / Family:</span>
                <span className="font-semibold">{focusNode.group || 'Independent'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Corporate Classification:</span>
                <span className="font-semibold">{focusNode.type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Headquarters Location:</span>
                <span className="font-semibold">{focusNode.properties.hq as string || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Country:</span>
                <span className="font-semibold">{focusNode.properties.country as string || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Credit Rating:</span>
                <span className="font-mono font-bold text-yellow-500">{focusNode.properties.creditRating as string || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Registry ID:</span>
                <span className="font-mono text-muted-foreground">{focusNode.id}</span>
              </div>
            </div>

            {focusNode.riskLevel && (
              <div className="p-3 border rounded-lg bg-muted/30">
                <div className="flex items-center gap-2 font-bold text-xs">
                  <span className={`w-2.5 h-2.5 rounded-full ${focusNode.riskLevel === 'high' ? 'bg-red-500 animate-pulse' : focusNode.riskLevel === 'medium' ? 'bg-amber-500' : 'bg-green-500'}`} />
                  Credit Default Risk: <span className="uppercase text-primary">{focusNode.riskLevel}</span>
                </div>
                {focusNode.riskDescription && (
                  <p className="text-[10px] text-muted-foreground mt-1.5 leading-relaxed">{focusNode.riskDescription}</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Downstream Structure (Subsidiaries & Affiliates) */}
        <Card className="bg-card/30 flex flex-col">
          <CardHeader
            onClick={() => toggleSection('subsidiaries')}
            className="p-4 pb-2 border-b cursor-pointer flex flex-row items-center justify-between bg-card/30"
          >
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Network className="w-4 h-4 text-green-400" />
              Downstream Subsidiaries (Ownership Tree)
            </CardTitle>
            <span className="text-xs text-muted-foreground">
              {expandedSections.subsidiaries ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </span>
          </CardHeader>
          {expandedSections.subsidiaries && (
            <CardContent className="p-3 flex-1">
              {nestedSubsidiaries.length === 0 ? (
                <div className="p-8 border border-dashed rounded-lg text-center text-xs text-muted-foreground">
                  No downstream subsidiaries owned.
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  {nestedSubsidiaries.map((item) => renderTreeNode(item, 'down'))}
                </div>
              )}
            </CardContent>
          )}
        </Card>
      </div>

      {/* Board & Key Personnel Management */}
      <Card className="bg-card/30">
        <CardHeader
          onClick={() => toggleSection('management')}
          className="p-4 pb-2 border-b cursor-pointer flex flex-row items-center justify-between bg-card/30"
        >
          <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-purple-400" />
            Board Members & Executive Officers Connections
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {expandedSections.management ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </span>
        </CardHeader>
        {expandedSections.management && (
          <CardContent className="p-3">
            {executives.length === 0 ? (
              <p className="text-xs text-muted-foreground italic p-2">No key executive registry files found.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {executives.map(({ node, edge }) => (
                  <div
                    key={node.id}
                    onClick={() => onSetFocusEntity(node.id)}
                    className="p-3 border rounded-lg bg-card/60 hover:bg-muted/30 cursor-pointer flex items-center justify-between"
                  >
                    <div>
                      <div className="font-extrabold text-xs text-foreground">{node.label}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">{edge.relation}</div>
                    </div>
                    <span className="text-[9px] bg-purple-500/20 text-purple-400 border border-purple-500/30 px-1.5 py-0.5 rounded font-black uppercase">
                      Executive
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        )}
      </Card>
    </div>
  )
}
