import { useMemo, useState, useEffect } from 'react'
import type { GraphData, GraphNode } from '../types/graph'
import { Card, CardContent, CardHeader, CardTitle, Button } from '@finiq/ui'
import { AlertOctagon, RefreshCw, ShieldAlert, Sparkles, ToggleRight } from 'lucide-react'

interface KOGridViewProps {
  graph: GraphData
  focusEntityId: string
  onSetFocusEntity: (id: string) => void
  onGraphUpdate: (graph: GraphData) => void
}

export function KOGridView(props: KOGridViewProps) {
  const { graph, focusEntityId, onSetFocusEntity, onGraphUpdate } = props
  const [manualDefaults, setManualDefaults] = useState<Record<string, boolean>>({})

  // Resolve focus node
  const focusNode = useMemo(
    () => graph.nodes.find((n) => n.id === focusEntityId) || graph.nodes[0],
    [graph.nodes, focusEntityId]
  )

  const toId = (val: string | GraphNode): string => (typeof val === 'string' ? val : val.id)

  // Risk Propagation Engine
  const propagatedGraph = useMemo(() => {
    // 1. Initialize nodes with default risk levels and base properties
    const nodes = graph.nodes.map((node) => {
      const isManual = manualDefaults[node.id]
      return {
        ...node,
        riskLevel: (isManual ? 'high' : 'low') as 'low' | 'medium' | 'high',
        riskDescription: isManual ? 'User-triggered default credit risk.' : '',
      }
    })

    const edges = graph.edges

    // 2. Propagation Loop (up to 3 iterations for depth resolving)
    for (let iter = 0; iter < 3; iter++) {
      let changed = false

      nodes.forEach((node) => {
        // Skip nodes already user-flagged as high default risk
        if (manualDefaults[node.id]) return

        const nodeId = node.id
        let maxRisk: 'low' | 'medium' | 'high' = 'low'
        let reasons: string[] = []

        // A. Supplier defaults (inbound transactions)
        const suppliers = edges.filter((e) => toId(e.target) === nodeId && e.category === 'transaction')
        let highRiskSupplierCostShare = 0
        suppliers.forEach((edge) => {
          const supplierNode = nodes.find((n) => n.id === toId(edge.source))
          if (supplierNode && supplierNode.riskLevel === 'high') {
            highRiskSupplierCostShare += edge.weight || 0
            reasons.push(`${supplierNode.label} default (cost: ${edge.weight}%)`)
          }
        })

        if (highRiskSupplierCostShare > 30) {
          maxRisk = 'high'
        } else if (highRiskSupplierCostShare > 15) {
          maxRisk = 'medium'
        }

        // B. Customer defaults (outbound transactions)
        const customers = edges.filter((e) => toId(e.source) === nodeId && e.category === 'transaction')
        let highRiskCustomerRevShare = 0
        customers.forEach((edge) => {
          const customerNode = nodes.find((n) => n.id === toId(edge.target))
          if (customerNode && customerNode.riskLevel === 'high') {
            highRiskCustomerRevShare += edge.weight || 0
            reasons.push(`${customerNode.label} default (rev: ${edge.weight}%)`)
          }
        })

        if (highRiskCustomerRevShare > 30) {
          maxRisk = 'high'
        } else if (highRiskCustomerRevShare > 15 && (maxRisk as string) !== 'high') {
          maxRisk = 'medium'
        }

        // C. Shareholder/Parent defaults (inbound equity)
        const owners = edges.filter((e) => toId(e.target) === nodeId && e.category === 'equity')
        owners.forEach((edge) => {
          const ownerNode = nodes.find((n) => n.id === toId(edge.source))
          if (ownerNode && ownerNode.riskLevel === 'high') {
            const stake = edge.weight || 0
            if (stake > 30) {
              maxRisk = 'high'
              reasons.push(`Parent ${ownerNode.label} default (stake: ${stake}%)`)
            } else if (stake > 10 && (maxRisk as string) !== 'high') {
              maxRisk = 'medium'
              reasons.push(`Parent ${ownerNode.label} default (stake: ${stake}%)`)
            }
          }
        })

        if (node.riskLevel !== maxRisk) {
          node.riskLevel = maxRisk
          node.riskDescription = reasons.join(', ')
          changed = true
        }
      })

      if (!changed) break
    }

    return { nodes, edges }
  }, [graph, manualDefaults])

  // Sync risk updates back to graph state when risk changes
  useEffect(() => {
    // Deep equal check to prevent infinite loop
    let needsUpdate = false
    propagatedGraph.nodes.forEach((n, idx) => {
      const orig = graph.nodes[idx]
      if (orig && (orig.riskLevel !== n.riskLevel || orig.riskDescription !== n.riskDescription)) {
        needsUpdate = true
      }
    })
    if (needsUpdate) {
      onGraphUpdate(propagatedGraph)
    }
  }, [propagatedGraph, graph.nodes, onGraphUpdate])

  const toggleManualDefault = (id: string) => {
    setManualDefaults((prev) => ({
      ...prev,
      [id]: !prev[id],
    }))
  }

  const resetAllDefaults = () => {
    setManualDefaults({})
  }

  // Group corporate nodes by relationship structure to Focus node
  const matrixData = useMemo(() => {
    const focusId = focusNode?.id || ''
    return propagatedGraph.nodes.map((node) => {
      // Find relationship description to focus node
      const edge = propagatedGraph.edges.find(
        (e) =>
          (toId(e.source) === focusId && toId(e.target) === node.id) ||
          (toId(e.source) === node.id && toId(e.target) === focusId)
      )

      let relationText = 'Network Entity'
      if (node.id === focusId) {
        relationText = 'Focus Entity'
      } else if (edge) {
        if (toId(edge.source) === focusId) {
          relationText = `${edge.relation} (Outbound)`
        } else {
          relationText = `${edge.relation} (Inbound)`
        }
      }

      return {
        ...node,
        relationText,
      }
    })
  }, [propagatedGraph, focusNode])

  // Split nodes by hierarchical tier
  const tierMatrix = useMemo(() => {
    const focusId = focusNode?.id || ''
    const parents: typeof matrixData = []
    const targets: typeof matrixData = []
    const subsidiaries: typeof matrixData = []
    const others: typeof matrixData = []

    matrixData.forEach((item) => {
      if (item.id === focusId) {
        targets.push(item)
      } else {
        const edge = propagatedGraph.edges.find(
          (e) =>
            (toId(e.source) === focusId && toId(e.target) === item.id) ||
            (toId(e.source) === item.id && toId(e.target) === focusId)
        )
        if (edge && toId(edge.target) === focusId && edge.category === 'equity') {
          parents.push(item)
        } else if (edge && toId(edge.source) === focusId && edge.category === 'equity') {
          subsidiaries.push(item)
        } else {
          others.push(item)
        }
      }
    })

    return { parents, targets, subsidiaries, others }
  }, [matrixData, focusNode, propagatedGraph])

  const getRiskStyles = (level?: string) => {
    if (level === 'high') return 'bg-red-500/10 border-red-500/30 text-red-500 animate-pulse-fast'
    if (level === 'medium') return 'bg-amber-500/10 border-amber-500/30 text-amber-500'
    return 'bg-green-500/10 border-green-500/30 text-green-500'
  }

  const getRowRiskColor = (level?: string) => {
    if (level === 'high') return 'bg-red-950/10 hover:bg-red-950/20 text-red-400 font-bold border-l-4 border-l-red-500'
    if (level === 'medium') return 'bg-amber-950/10 hover:bg-amber-950/20 text-amber-400 border-l-4 border-l-amber-500'
    return 'hover:bg-muted/40 border-l-4 border-l-transparent'
  }

  return (
    <div className="flex flex-col gap-6 h-full overflow-y-auto p-4 bg-background/40 backdrop-blur-sm text-foreground">
      {/* KOgrid Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 border rounded-xl bg-card/60">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-red-500 animate-bounce" />
            KOgrid Risk propagation Simulator
          </h2>
          <p className="text-xs text-muted-foreground">
            Analyze systemic default contagion paths, credit ranking matrices, and network vulnerabilities in real time.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={resetAllDefaults}
          className="text-xs flex items-center gap-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Reset Simulation
        </Button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Simulation Controls (Left Sidebar) */}
        <Card className="xl:col-span-1 bg-card/30 self-start">
          <CardHeader className="p-4 pb-2 border-b bg-card/30">
            <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <ToggleRight className="w-4 h-4 text-primary" /> Trigger Credit Default
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-3">
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              Click toggles to artificially trigger a credit default (Risk ➔ HIGH) for an entity. The algorithm will automatically propagate credit risk to all dependent entities.
            </p>

            <div className="space-y-2 border-t pt-3 max-h-[400px] overflow-y-auto pr-1">
              {propagatedGraph.nodes.map((node) => {
                const isDefaulted = manualDefaults[node.id] || false
                return (
                  <div
                    key={node.id}
                    className={`flex items-center justify-between p-2 border rounded-lg transition-all ${isDefaulted ? 'bg-red-500/10 border-red-500/30' : 'bg-muted/10'}`}
                  >
                    <div className="min-w-0">
                      <div className="font-bold text-xs truncate">{node.label}</div>
                      <div className="text-[9px] text-muted-foreground">{node.type}</div>
                    </div>
                    <button
                      onClick={() => toggleManualDefault(node.id)}
                      className="p-1 text-muted-foreground hover:text-primary transition-colors shrink-0"
                    >
                      {isDefaulted ? (
                        <div className="text-xs font-black text-red-500 border border-red-500/30 px-1.5 py-0.5 rounded bg-red-950/20">
                          DEFAULT
                        </div>
                      ) : (
                        <div className="text-xs font-medium text-muted-foreground border px-1.5 py-0.5 rounded bg-background hover:bg-muted">
                          Normal
                        </div>
                      )}
                    </button>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* Credit Matrix & Organization Grid (Right Side) */}
        <div className="xl:col-span-3 flex flex-col gap-6">
          {/* Layered Group Organizational Grid Chart */}
          <Card className="bg-card/30">
            <CardHeader className="p-4 pb-2 border-b bg-card/30">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-yellow-500" /> Organizational Control Grid Matrix
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              {/* Parents Layer */}
              <div className="grid grid-cols-5 gap-2 items-center">
                <div className="col-span-1 text-[10px] font-bold text-muted-foreground uppercase text-right pr-2">Parents:</div>
                <div className="col-span-4 flex flex-wrap gap-2">
                  {tierMatrix.parents.length === 0 ? (
                    <span className="text-[10px] text-muted-foreground italic">No parent shareholders</span>
                  ) : (
                    tierMatrix.parents.map((node) => (
                      <div
                        key={node.id}
                        onClick={() => onSetFocusEntity(node.id)}
                        className={`px-3 py-2 border rounded-lg text-xs cursor-pointer flex flex-col gap-0.5 ${getRiskStyles(node.riskLevel)}`}
                      >
                        <span className="font-bold">{node.label}</span>
                        <span className="text-[9px] text-muted-foreground">Rating: {node.properties.creditRating as string || 'N/A'}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Target Entity Layer */}
              <div className="grid grid-cols-5 gap-2 items-center border-y py-3 bg-muted/10">
                <div className="col-span-1 text-[10px] font-bold text-primary uppercase text-right pr-2">Focus:</div>
                <div className="col-span-4">
                  {tierMatrix.targets.map((node) => (
                    <div
                      key={node.id}
                      className={`inline-flex flex-col gap-0.5 px-4 py-2 border-2 rounded-xl text-sm font-black shadow-lg ${getRiskStyles(node.riskLevel)}`}
                    >
                      <span>{node.label}</span>
                      <span className="text-[10px] font-medium opacity-80">Sector: {node.properties.sector as string || 'N/A'}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Subsidiaries Layer */}
              <div className="grid grid-cols-5 gap-2 items-center">
                <div className="col-span-1 text-[10px] font-bold text-muted-foreground uppercase text-right pr-2">Subsidiaries:</div>
                <div className="col-span-4 flex flex-wrap gap-2">
                  {tierMatrix.subsidiaries.length === 0 ? (
                    <span className="text-[10px] text-muted-foreground italic">No direct subsidiaries</span>
                  ) : (
                    tierMatrix.subsidiaries.map((node) => (
                      <div
                        key={node.id}
                        onClick={() => onSetFocusEntity(node.id)}
                        className={`px-3 py-2 border rounded-lg text-xs cursor-pointer flex flex-col gap-0.5 ${getRiskStyles(node.riskLevel)}`}
                      >
                        <span className="font-bold">{node.label}</span>
                        <span className="text-[9px] text-muted-foreground">Rating: {node.properties.creditRating as string || 'N/A'}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Structured Credit Risk Grid Matrix */}
          <Card className="bg-card/30">
            <CardHeader className="p-4 pb-2 border-b bg-card/30">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <AlertOctagon className="w-4 h-4 text-muted-foreground" /> Credit Matrix Registry
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b bg-muted/40 text-muted-foreground uppercase font-bold">
                    <th className="p-3">Entity Name</th>
                    <th className="p-3">Relationship Type</th>
                    <th className="p-3">Credit Rating</th>
                    <th className="p-3">Simulation Default Risk</th>
                    <th className="p-3">Contagion Cause</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {matrixData.map((node) => (
                    <tr
                      key={node.id}
                      onClick={() => onSetFocusEntity(node.id)}
                      className={`cursor-pointer transition-colors ${getRowRiskColor(node.riskLevel)}`}
                    >
                      <td className="p-3 font-bold">{node.label}</td>
                      <td className="p-3 font-semibold text-muted-foreground">{node.relationText}</td>
                      <td className="p-3 font-mono font-bold text-yellow-500">
                        {node.properties.creditRating as string || 'N/A'}
                      </td>
                      <td className="p-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black uppercase border ${node.riskLevel === 'high' ? 'bg-red-500/10 border-red-500 text-red-500' : node.riskLevel === 'medium' ? 'bg-amber-500/10 border-amber-500 text-amber-500' : 'bg-green-500/10 border-green-500 text-green-500'}`}>
                          {node.riskLevel || 'low'}
                        </span>
                      </td>
                      <td className="p-3 text-[10px] text-red-400 font-semibold max-w-[200px] truncate">
                        {node.riskDescription || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
