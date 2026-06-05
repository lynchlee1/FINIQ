import { useMemo, useState } from 'react'
import type { GraphData, GraphNode, GraphEdge } from '../types/graph'
import { Card, CardContent, CardHeader, CardTitle } from '@finiq/ui'
import { ArrowRight, Globe, Layers, Shield, Sparkles, TrendingUp, AlertTriangle } from 'lucide-react'

interface SPLCViewProps {
  graph: GraphData
  focusEntityId: string
  onSetFocusEntity: (id: string) => void
}

export function SPLCView(props: SPLCViewProps) {
  const { graph, focusEntityId, onSetFocusEntity } = props
  const [minWeight, setMinWeight] = useState(0)

  // Resolve focus node
  const focusNode = useMemo(
    () => graph.nodes.find((n) => n.id === focusEntityId) || graph.nodes[0],
    [graph.nodes, focusEntityId]
  )

  const focusId = focusNode?.id || ''

  // Get edge source/target IDs cleanly
  const toId = (val: string | GraphNode): string => (typeof val === 'string' ? val : val.id)

  // Filter edges connected to focus node
  const relations = useMemo(() => {
    const inbound = graph.edges.filter((e) => toId(e.target) === focusId)
    const outbound = graph.edges.filter((e) => toId(e.source) === focusId)
    return { inbound, outbound }
  }, [graph.edges, focusId])

  // Extract suppliers, customers, competitors, and partners
  const suppliers = useMemo(() => {
    return relations.inbound
      .filter((e) => e.category === 'transaction' && e.weight >= minWeight)
      .map((e) => {
        const sourceNode = graph.nodes.find((n) => n.id === toId(e.source))
        return {
          node: sourceNode,
          edge: e,
        }
      })
      .filter((item) => item.node !== undefined) as { node: GraphNode; edge: GraphEdge }[]
  }, [relations.inbound, graph.nodes, minWeight])

  const customers = useMemo(() => {
    return relations.outbound
      .filter((e) => e.category === 'transaction' && e.weight >= minWeight)
      .map((e) => {
        const targetNode = graph.nodes.find((n) => n.id === toId(e.target))
        return {
          node: targetNode,
          edge: e,
        }
      })
      .filter((item) => item.node !== undefined) as { node: GraphNode; edge: GraphEdge }[]
  }, [relations.outbound, graph.nodes, minWeight])

  const competitors = useMemo(() => {
    const compEdges = graph.edges.filter(
      (e) =>
        (toId(e.source) === focusId || toId(e.target) === focusId) &&
        e.relation.toLowerCase().includes('competitor')
    )
    return compEdges
      .map((e) => {
        const sid = toId(e.source)
        const tid = toId(e.target)
        const peerId = sid === focusId ? tid : sid
        return graph.nodes.find((n) => n.id === peerId)
      })
      .filter((n) => n !== undefined) as GraphNode[]
  }, [graph.edges, graph.nodes, focusId])

  const partners = useMemo(() => {
    const partnerEdges = graph.edges.filter(
      (e) =>
        (toId(e.source) === focusId || toId(e.target) === focusId) &&
        (e.category === 'other' || e.category === 'personnel') &&
        !e.relation.toLowerCase().includes('competitor') &&
        !e.relation.toLowerCase().includes('subsidiary') &&
        !e.relation.toLowerCase().includes('shareholder') &&
        !e.relation.toLowerCase().includes('chairman')
    )
    return partnerEdges
      .map((e) => {
        const sid = toId(e.source)
        const tid = toId(e.target)
        const peerId = sid === focusId ? tid : sid
        const node = graph.nodes.find((n) => n.id === peerId)
        return node ? { node, edge: e } : null
      })
      .filter(Boolean) as { node: GraphNode; edge: GraphEdge }[]
  }, [graph.edges, graph.nodes, focusId])

  if (!focusNode) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Select a corporate entity to inspect supply chain.
      </div>
    )
  }

  const getRiskColor = (level?: string) => {
    if (level === 'high') return 'text-red-500 border-red-500 bg-red-950/20'
    if (level === 'medium') return 'text-amber-500 border-amber-500 bg-amber-950/20'
    return 'text-green-500 border-green-500 bg-green-950/20'
  }

  return (
    <div className="flex flex-col gap-6 h-full overflow-y-auto p-4 bg-background/40 backdrop-blur-sm text-foreground">
      {/* SPLC Header Control */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 border rounded-xl bg-card/60">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            Bloomberg SPLC Studio: {focusNode.label}
          </h2>
          <p className="text-xs text-muted-foreground">
            Visualizing direct industrial supply chains, cost allocations, and customer revenues.
          </p>
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <span className="text-xs font-semibold whitespace-nowrap">Min Transaction Weight:</span>
          <input
            type="range"
            min="0"
            max="40"
            value={minWeight}
            onChange={(e) => setMinWeight(Number(e.target.value))}
            className="w-32 h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
          />
          <span className="text-xs font-bold bg-primary/20 px-2 py-0.5 rounded text-primary min-w-[32px] text-center">
            {minWeight}%
          </span>
        </div>
      </div>

      {/* SPLC Flow Diagram */}
      <div className="grid grid-cols-1 lg:grid-cols-7 gap-4 items-center justify-center p-4 border rounded-xl bg-card/20 min-h-[300px]">
        {/* Suppliers Column */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1 text-center flex items-center justify-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 rotate-180 text-blue-400" />
            Suppliers (Inbound Cost)
          </div>
          {suppliers.length === 0 ? (
            <div className="p-6 border border-dashed rounded-lg text-center text-xs text-muted-foreground">
              No suppliers found.
            </div>
          ) : (
            suppliers.map(({ node, edge }) => (
              <Card
                key={node.id}
                onClick={() => onSetFocusEntity(node.id)}
                className="cursor-pointer border-l-4 border-l-blue-500 hover:scale-[1.02] transition-transform duration-200 bg-card/80 hover:shadow-lg"
              >
                <CardContent className="p-3 flex items-center justify-between">
                  <div className="min-w-0">
                    <div className="font-bold text-sm truncate">{node.label}</div>
                    <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                      <Globe className="w-3 h-3" /> {node.properties.country as string || 'N/A'}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-xs font-black text-blue-400">Cost: {edge.weight}%</span>
                    <span className={`text-[9px] px-1 rounded uppercase font-bold border ${getRiskColor(node.riskLevel)}`}>
                      {node.riskLevel || 'low'}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Arrow to Center */}
        <div className="hidden lg:flex lg:col-span-1 justify-center">
          <ArrowRight className="w-8 h-8 text-blue-500/50 animate-pulse" />
        </div>

        {/* Central Focus Entity */}
        <div className="lg:col-span-1 flex justify-center">
          <div className="w-full max-w-[200px] aspect-square rounded-2xl bg-gradient-to-br from-primary via-primary/80 to-blue-600 p-0.5 shadow-2xl flex flex-col justify-between text-white overflow-hidden relative group">
            <div className="absolute inset-0 bg-black/10 group-hover:bg-transparent transition-colors duration-200" />
            <div className="p-4 z-10 flex flex-col h-full justify-between">
              <div>
                <span className="text-[9px] uppercase font-black tracking-widest bg-white/20 px-2 py-0.5 rounded-full">
                  {focusNode.type}
                </span>
                <h3 className="font-extrabold text-base leading-tight mt-2 drop-shadow-md">{focusNode.label}</h3>
              </div>
              <div className="text-left">
                <div className="text-[10px] text-white/80 font-medium">HQ: {focusNode.properties.hq as string || 'N/A'}</div>
                <div className="text-[10px] text-white/80 font-medium flex items-center gap-1 mt-1">
                  <Shield className="w-3.5 h-3.5 text-yellow-300" /> Rating: {focusNode.properties.creditRating as string || 'N/A'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Arrow from Center */}
        <div className="hidden lg:flex lg:col-span-1 justify-center">
          <ArrowRight className="w-8 h-8 text-green-500/50 animate-pulse" />
        </div>

        {/* Customers Column */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1 text-center flex items-center justify-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-green-400" />
            Customers (Outbound Revenue)
          </div>
          {customers.length === 0 ? (
            <div className="p-6 border border-dashed rounded-lg text-center text-xs text-muted-foreground">
              No customers found.
            </div>
          ) : (
            customers.map(({ node, edge }) => (
              <Card
                key={node.id}
                onClick={() => onSetFocusEntity(node.id)}
                className="cursor-pointer border-l-4 border-l-green-500 hover:scale-[1.02] transition-transform duration-200 bg-card/80 hover:shadow-lg"
              >
                <CardContent className="p-3 flex items-center justify-between">
                  <div className="min-w-0">
                    <div className="font-bold text-sm truncate">{node.label}</div>
                    <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                      <Globe className="w-3 h-3" /> {node.properties.country as string || 'N/A'}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-xs font-black text-green-400">Rev: {edge.weight}%</span>
                    <span className={`text-[9px] px-1 rounded uppercase font-bold border ${getRiskColor(node.riskLevel)}`}>
                      {node.riskLevel || 'low'}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>

      {/* SPLC Detail Grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Suppliers Table */}
        <Card className="bg-card/40">
          <CardHeader className="p-4 pb-2 border-b bg-card/30">
            <CardTitle className="text-sm font-bold flex items-center gap-1.5 uppercase text-blue-400">
              <Layers className="w-4 h-4" /> Suppliers
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground uppercase font-bold">
                  <th className="p-3">Entity Name</th>
                  <th className="p-3 text-right">Cost Contribution</th>
                  <th className="p-3">Sector</th>
                  <th className="p-3">Credit Rating</th>
                  <th className="p-3">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {suppliers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-4 text-center text-muted-foreground">No supplier rows.</td>
                  </tr>
                ) : (
                  suppliers.map(({ node, edge }) => (
                    <tr
                      key={node.id}
                      onClick={() => onSetFocusEntity(node.id)}
                      className="hover:bg-muted/40 cursor-pointer transition-colors"
                    >
                      <td className="p-3 font-bold">{node.label}</td>
                      <td className="p-3 text-right font-black text-blue-400">{edge.weight}%</td>
                      <td className="p-3 text-muted-foreground">{node.properties.sector as string || '-'}</td>
                      <td className="p-3 font-mono">{node.properties.creditRating as string || '-'}</td>
                      <td className="p-3">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border uppercase ${getRiskColor(node.riskLevel)}`}>
                          {node.riskLevel || 'low'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Customers Table */}
        <Card className="bg-card/40">
          <CardHeader className="p-4 pb-2 border-b bg-card/30">
            <CardTitle className="text-sm font-bold flex items-center gap-1.5 uppercase text-green-400">
              <Layers className="w-4 h-4" /> Customers
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b bg-muted/30 text-muted-foreground uppercase font-bold">
                  <th className="p-3">Entity Name</th>
                  <th className="p-3 text-right">Revenue Contribution</th>
                  <th className="p-3">Sector</th>
                  <th className="p-3">Credit Rating</th>
                  <th className="p-3">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {customers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-4 text-center text-muted-foreground">No customer rows.</td>
                  </tr>
                ) : (
                  customers.map(({ node, edge }) => (
                    <tr
                      key={node.id}
                      onClick={() => onSetFocusEntity(node.id)}
                      className="hover:bg-muted/40 cursor-pointer transition-colors"
                    >
                      <td className="p-3 font-bold">{node.label}</td>
                      <td className="p-3 text-right font-black text-green-400">{edge.weight}%</td>
                      <td className="p-3 text-muted-foreground">{node.properties.sector as string || '-'}</td>
                      <td className="p-3 font-mono">{node.properties.creditRating as string || '-'}</td>
                      <td className="p-3">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border uppercase ${getRiskColor(node.riskLevel)}`}>
                          {node.riskLevel || 'low'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Competitors List */}
        <Card className="bg-card/40">
          <CardHeader className="p-4 pb-2 border-b bg-card/30">
            <CardTitle className="text-sm font-bold flex items-center gap-1.5 uppercase text-yellow-400">
              <AlertTriangle className="w-4 h-4 text-yellow-400" /> Competitors
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3">
            {competitors.length === 0 ? (
              <p className="text-xs text-muted-foreground italic p-2">No direct competitor relationships found.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {competitors.map((node) => (
                  <div
                    key={node.id}
                    onClick={() => onSetFocusEntity(node.id)}
                    className="p-3 border rounded-lg bg-card/60 hover:bg-muted/30 cursor-pointer flex items-center justify-between"
                  >
                    <div>
                      <div className="font-bold text-xs">{node.label}</div>
                      <div className="text-[10px] text-muted-foreground">{node.properties.hq as string || 'Global'}</div>
                    </div>
                    <span className="text-[10px] bg-yellow-400/20 text-yellow-500 font-bold border border-yellow-500/30 px-1.5 rounded uppercase">
                      Competitor
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Partners List */}
        <Card className="bg-card/40">
          <CardHeader className="p-4 pb-2 border-b bg-card/30">
            <CardTitle className="text-sm font-bold flex items-center gap-1.5 uppercase text-purple-400">
              <Globe className="w-4 h-4 text-purple-400" /> Strategic Partners & Alliances
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3">
            {partners.length === 0 ? (
              <p className="text-xs text-muted-foreground italic p-2">No partner alliances mapped.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {partners.map(({ node, edge }) => (
                  <div
                    key={node.id}
                    onClick={() => onSetFocusEntity(node.id)}
                    className="p-3 border rounded-lg bg-card/60 hover:bg-muted/30 cursor-pointer flex items-center justify-between"
                  >
                    <div>
                      <div className="font-bold text-xs">{node.label}</div>
                      <div className="text-[10px] text-muted-foreground italic">{edge.relation}</div>
                    </div>
                    <span className="text-[10px] bg-purple-400/20 text-purple-400 font-bold border border-purple-500/30 px-1.5 rounded uppercase">
                      Partner
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
