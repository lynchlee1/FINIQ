import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { forceCollide, forceLink, forceManyBody, forceX, forceY } from 'd3-force'
import { Button } from '@finiq/ui'
import type { GraphData, GraphEdge, GraphNode, GraphStyleConfig, LayoutConfig, NodeShape, NodeTypeStyle } from '../types/graph'
import type { GraphContextActionHandler, GraphEdgeContextAction, GraphNodeContextAction } from '../core'

interface ContextMenuState {
  x: number
  y: number
  kind: 'node' | 'edge'
  id: string
}

export interface GraphCanvasContextAction {
  label: string
  action: GraphNodeContextAction | GraphEdgeContextAction
}

export interface GraphCanvasContextMenuItem<TAction extends GraphNodeContextAction | GraphEdgeContextAction> {
  label: string
  action: TAction
}

export interface GraphCanvasContextMenuItems {
  node?: GraphCanvasContextMenuItem<GraphNodeContextAction>[]
  edge?: GraphCanvasContextMenuItem<GraphEdgeContextAction>[]
}

export interface GraphCanvasProps {
  graph: GraphData
  degreeMap: Map<string, number>
  style: GraphStyleConfig
  layout: LayoutConfig
  selectedNodeIds: Set<string>
  selectedEdgeIds: Set<string>
  highlightedNodeIds: Set<string>
  highlightedEdgeIds: Set<string>
  simulationRunning: boolean
  onSimulationToggle: (running: boolean) => void
  onNodeClick: (node: GraphNode, multiSelect: boolean) => void
  onEdgeClick: (edge: GraphEdge) => void
  onBackgroundClick: () => void
  onNodeHover: (node: GraphNode | null) => void
  onContextAction: GraphContextActionHandler
  onVisibleBounds: (width: number, height: number) => void
  jumpToNodeId?: string
  showToolbar?: boolean
  contextMenuItems?: GraphCanvasContextMenuItems
  onUnpinAll?: () => void
}

function truncateLabel(label: string, maxLength: number): string {
  if (label.length <= maxLength) {
    return label
  }
  return `${label.slice(0, Math.max(0, maxLength - 1))}…`
}

function drawNodeShape(ctx: CanvasRenderingContext2D, shape: NodeShape, x: number, y: number, radius: number): void {
  ctx.beginPath()
  if (shape === 'square') {
    const side = radius * 1.7
    ctx.rect(x - side / 2, y - side / 2, side, side)
  } else if (shape === 'diamond') {
    ctx.moveTo(x, y - radius)
    ctx.lineTo(x + radius, y)
    ctx.lineTo(x, y + radius)
    ctx.lineTo(x - radius, y)
    ctx.closePath()
  } else if (shape === 'triangle') {
    ctx.moveTo(x, y - radius * 1.08)
    ctx.lineTo(x + radius * 1.08, y + radius * 0.85)
    ctx.lineTo(x - radius * 1.08, y + radius * 0.85)
    ctx.closePath()
  } else {
    ctx.arc(x, y, radius, 0, 2 * Math.PI)
  }
}

export function GraphCanvas(props: GraphCanvasProps) {
  const {
    graph,
    degreeMap,
    style,
    layout,
    selectedNodeIds,
    selectedEdgeIds,
    highlightedNodeIds,
    highlightedEdgeIds,
    simulationRunning,
    onSimulationToggle,
    onNodeClick,
    onEdgeClick,
    onBackgroundClick,
    onNodeHover,
    onContextAction,
    onVisibleBounds,
    jumpToNodeId,
    showToolbar = true,
    contextMenuItems,
    onUnpinAll,
  } = props

  const containerRef = useRef<HTMLDivElement | null>(null)
  const fgRef = useRef<ForceGraphMethods<GraphNode, GraphEdge> | undefined>(undefined)
  const [size, setSize] = useState({ width: 1200, height: 800 })
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const forceGraphData = useMemo(
    () => ({ nodes: graph.nodes, links: graph.edges }),
    [graph.nodes, graph.edges],
  )

  useEffect(() => {
    const element = containerRef.current
    if (!element) return

    const resize = () => {
      const rect = element.getBoundingClientRect()
      setSize({ width: Math.max(300, rect.width), height: Math.max(300, rect.height) })
      onVisibleBounds(Math.max(300, rect.width), Math.max(300, rect.height))
    }

    // Initial resize
    resize()

    // Use ResizeObserver to detect flex container size changes
    const observer = new ResizeObserver(() => {
      resize()
    })
    observer.observe(element)

    // Fallback window resize just in case
    window.addEventListener('resize', resize)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', resize)
    }
  }, [onVisibleBounds])

  useEffect(() => {
    if (!fgRef.current) {
      return
    }
    const linkForce = forceLink<GraphNode, GraphEdge>()
      .id((node: GraphNode) => String(node.id))
      .distance(layout.linkDistance) as unknown as (alpha: number) => void
    fgRef.current
      .d3Force('charge', forceManyBody().strength(layout.chargeStrength).distanceMax(600))
      .d3Force('link', linkForce)
      .d3Force('collide', forceCollide(layout.collisionRadius))
      .d3Force('x', forceX((d: any) => d.userX ?? 0).strength((d: any) => d.userX !== undefined ? 0.08 : 0.015))
      .d3Force('y', forceY((d: any) => d.userY ?? 0).strength((d: any) => d.userY !== undefined ? 0.08 : 0.015))
    if (simulationRunning) {
      fgRef.current.d3ReheatSimulation()
    }
  }, [layout.chargeStrength, layout.collisionRadius, layout.linkDistance, graph, simulationRunning])

  useEffect(() => {
    if (!fgRef.current || !simulationRunning) {
      return
    }
    fgRef.current.d3ReheatSimulation()
  }, [simulationRunning])

  useEffect(() => {
    if (!jumpToNodeId || !fgRef.current) {
      return
    }
    const node = graph.nodes.find((n) => n.id === jumpToNodeId)
    if (!node || typeof node.x !== 'number' || typeof node.y !== 'number') {
      return
    }
    fgRef.current.centerAt(node.x, node.y, 600)
    fgRef.current.zoom(4, 600)
  }, [jumpToNodeId, graph.nodes])

  // Track double click
  const lastClickRef = useRef<{ id: string; time: number } | null>(null);
  const pinnedHistoryRef = useRef<string[]>([]);

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>()
    graph.nodes.forEach((node) => map.set(node.id, node))
    return map
  }, [graph.nodes])

  const activeContextMenuItems = useMemo(() => {
    if (!contextMenu) {
      return []
    }
    if (contextMenu.kind === 'node') {
      const node = nodeById.get(contextMenu.id)
      if (contextMenuItems?.node && contextMenuItems.node.length > 0) {
        return contextMenuItems.node
      }
      return [
        { label: node?.pinned ? 'Unpin node' : 'Pin node', action: node?.pinned ? 'unpin' : 'pin' },
        { label: 'Show neighbors', action: 'neighbors' },
        { label: 'Hide node', action: 'hide' },
        { label: 'Delete node', action: 'delete' },
      ]
    }

    if (contextMenuItems?.edge && contextMenuItems.edge.length > 0) {
      return contextMenuItems.edge
    }
    return [
      { label: 'Hide edge', action: 'hide' },
      { label: 'Delete edge', action: 'delete' },
    ]
  }, [contextMenu, contextMenuItems, nodeById])

  const closeContextMenu = () => setContextMenu(null)

  const nodeRuleStyle = (node: GraphNode): { color?: string; size?: number } => {
    let color: string | undefined
    let size: number | undefined
    for (const rule of style.styleRules) {
      if (rule.target !== 'node') {
        continue
      }
      let candidate: string | number
      if (rule.field === 'type') {
        candidate = node.type
      } else if (rule.field === 'group') {
        candidate = node.group ?? ''
      } else if (rule.field === 'tag') {
        candidate = node.tags.join(',')
      } else if (rule.field === 'degree') {
        candidate = degreeMap.get(node.id) ?? 0
      } else {
        continue
      }
      const numeric = Number(candidate)
      const ruleValue = Number(rule.value)
      const ruleValue2 = Number(rule.value2 ?? rule.value)
      const matched =
        rule.operator === 'equals'
          ? String(candidate) === rule.value
          : rule.operator === 'contains'
            ? String(candidate).includes(rule.value)
            : rule.operator === 'gte'
              ? Number.isFinite(numeric) && numeric >= ruleValue
              : rule.operator === 'lte'
                ? Number.isFinite(numeric) && numeric <= ruleValue
                : Number.isFinite(numeric) && numeric >= Math.min(ruleValue, ruleValue2) && numeric <= Math.max(ruleValue, ruleValue2)
      if (matched) {
        color = rule.color
        size = rule.size
      }
    }
    return { color, size }
  }

  const nodeTypeStyle = (node: GraphNode): NodeTypeStyle => {
    const override = style.nodeTypeStyles?.[node.type]
    return {
      color: override?.color ?? style.nodeColor,
      size: override?.size ?? style.nodeSize,
      shape: override?.shape ?? 'circle',
      borderColor: override?.borderColor ?? style.nodeBorderColor,
      borderWidth: override?.borderWidth ?? style.nodeBorderWidth,
    }
  }

  const edgeRuleStyle = (edge: GraphEdge): { color?: string; size?: number } => {
    let color: string | undefined
    let size: number | undefined
    for (const rule of style.styleRules) {
      if (rule.target !== 'edge') {
        continue
      }
      let candidate: string | number
      if (rule.field === 'relation') {
        candidate = edge.relation
      } else if (rule.field === 'weight') {
        candidate = edge.weight
      } else {
        continue
      }
      const numeric = Number(candidate)
      const ruleValue = Number(rule.value)
      const ruleValue2 = Number(rule.value2 ?? rule.value)
      const matched =
        rule.operator === 'equals'
          ? String(candidate) === rule.value
          : rule.operator === 'contains'
            ? String(candidate).includes(rule.value)
            : rule.operator === 'gte'
              ? Number.isFinite(numeric) && numeric >= ruleValue
              : rule.operator === 'lte'
                ? Number.isFinite(numeric) && numeric <= ruleValue
                : Number.isFinite(numeric) && numeric >= Math.min(ruleValue, ruleValue2) && numeric <= Math.max(ruleValue, ruleValue2)
      if (matched) {
        color = rule.color
        size = rule.size
      }
    }
    return { color, size }
  }

  return (
    <div className="relative w-full h-full" style={{ background: style.backgroundColor }} onClick={closeContextMenu}>
      {showToolbar ? (
        <div className="absolute top-4 left-4 z-10 flex gap-2 p-1.5 bg-card/80 backdrop-blur border rounded-lg shadow-xl">
          <Button
            variant="outline"
            size="xs"
            onClick={(event) => {
              event.stopPropagation()
              fgRef.current?.zoomToFit(600, 50)
            }}
            className="h-7 px-2 text-[11px] font-bold uppercase tracking-tight"
          >
            Fit View
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={(event) => {
              event.stopPropagation()
              if (!containerRef.current) return
              if (!document.fullscreenElement) {
                void containerRef.current.requestFullscreen()
              } else {
                void document.exitFullscreen()
              }
            }}
            className="h-7 px-2 text-[11px] font-bold uppercase tracking-tight"
          >
            Fullscreen
          </Button>
          {onUnpinAll && (
            <Button
              variant="outline"
              size="xs"
              onClick={(event) => {
                event.stopPropagation()
                graph.nodes.forEach((n: any) => {
                  delete n.fx
                  delete n.fy
                })
                onUnpinAll()
                if (!simulationRunning) {
                  onSimulationToggle(true)
                }
                fgRef.current?.d3ReheatSimulation()
              }}
              className="h-7 px-2 text-[11px] font-bold uppercase tracking-tight"
            >
              Unpin All
            </Button>
          )}
        </div>
      ) : null}

      <ForceGraph2D<GraphNode, GraphEdge>
        ref={fgRef}
        graphData={forceGraphData}
        width={size.width}
        height={size.height}
        backgroundColor={style.backgroundColor}
        warmupTicks={simulationRunning ? 0 : 100}
        cooldownTicks={simulationRunning ? Infinity : 0}
        d3AlphaDecay={layout.alphaDecay}
        onEngineStop={() => {
          if (simulationRunning) {
            onSimulationToggle(false)
          }
        }}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const overrides = nodeRuleStyle(node)
          const typeStyle = nodeTypeStyle(node)
          const isSelected = selectedNodeIds.has(node.id)
          const isHighlighted = highlightedNodeIds.has(node.id)
          const baseSize = overrides.size ?? typeStyle.size
          const radius = (baseSize + (isSelected ? 1.5 : 0)) * (isHighlighted ? 1.25 : 1)
          const opacity = isSelected ? 1 : style.nodeOpacity
          const fill = isSelected
            ? style.selectedColor
            : isHighlighted
              ? style.highlightedColor
              : (overrides.color ?? typeStyle.color)

          ctx.save()
          ctx.globalAlpha = opacity
          drawNodeShape(ctx, typeStyle.shape, node.x ?? 0, node.y ?? 0, radius)
          ctx.fillStyle = fill
          ctx.fill()
          ctx.lineWidth = typeStyle.borderWidth
          ctx.strokeStyle = typeStyle.borderColor
          ctx.stroke()

          // Draw Risk Indicator
          if (node.riskLevel && node.riskLevel !== 'low') {
            ctx.beginPath()
            ctx.arc(node.x ?? 0, node.y ?? 0, radius + 2, 0, 2 * Math.PI)
            ctx.strokeStyle = node.riskLevel === 'high' ? '#ef4444' : '#f59e0b'
            ctx.lineWidth = 1.5
            ctx.setLineDash([2, 2])
            ctx.stroke()
            ctx.setLineDash([])
          }

          ctx.restore()

          const showLabel =
            style.labelVisible && (globalScale >= style.labelVisibilityZoom || isSelected || isHighlighted)
          if (showLabel) {
            ctx.font = `${style.labelFontSize / globalScale}px Inter, sans-serif`
            ctx.fillStyle = '#e5e7eb'
            const text = truncateLabel(node.label, style.maxLabelLength)
            ctx.fillText(text, (node.x ?? 0) + radius + 1.5, (node.y ?? 0) - radius - 1)
          }
        }}
        linkColor={(edge) => {
          const overrides = edgeRuleStyle(edge)
          if (selectedEdgeIds.has(edge.id)) {
            return style.selectedColor
          }
          if (highlightedEdgeIds.has(edge.id)) {
            return style.highlightedColor
          }
          return overrides.color ?? style.edgeColor
        }}
        linkWidth={(edge) =>
          (selectedEdgeIds.has(edge.id) ? 2.2 : (edgeRuleStyle(edge).size ?? style.edgeWidth)) + (edge.weight ? Math.log10(Math.max(1, edge.weight)) * 0.5 : 0)
        }
        linkLineDash={(edge) => edge.is_active === false ? [4, 4] : null}
        linkCurvature={(edge) => edge.curvature ?? 0}
        linkDirectionalArrowLength={(edge) =>
          (style.arrowVisibility && edge.directed) ? Math.min(8, 3.5 + (edge.weight ? Math.log10(Math.max(1, edge.weight)) * 1.5 : 0)) : 0
        }
        linkDirectionalArrowRelPos={0.85}
        onNodeClick={(node, event) => {
          const now = Date.now();
          const lastClick = lastClickRef.current;
          
          if (lastClick && lastClick.id === node.id && now - lastClick.time < 300) {
            // Double click
            if (typeof node.x === 'number' && typeof node.y === 'number' && fgRef.current) {
              fgRef.current.centerAt(node.x, node.y, 600);
              fgRef.current.zoom(4, 600);
            }
            lastClickRef.current = null; // reset
          } else {
            lastClickRef.current = { id: node.id, time: now };
            onNodeClick(node, event.shiftKey);
          }

          // Pin action on every click
          node.fx = node.x;
          node.fy = node.y;
          pinnedHistoryRef.current.push(node.id);
          
          if (layout.pinLimit !== undefined && layout.pinLimit > 0) {
            while (pinnedHistoryRef.current.length > layout.pinLimit) {
              const oldestId = pinnedHistoryRef.current.shift();
              if (oldestId && !pinnedHistoryRef.current.includes(oldestId)) {
                const oldestNode = graph.nodes.find(n => n.id === oldestId) as any;
                if (oldestNode) {
                  delete oldestNode.fx;
                  delete oldestNode.fy;
                }
                onContextAction('node', oldestId, 'unpin');
              }
            }
          }

          onContextAction('node', node.id, 'pin');
          
          if (!simulationRunning) {
            onSimulationToggle(true);
          }
          fgRef.current?.d3ReheatSimulation();
        }}
        onNodeHover={(node) => onNodeHover(node)}
        onNodeRightClick={(node, event) => {
          event.preventDefault()
          setContextMenu({ x: event.clientX, y: event.clientY, kind: 'node', id: node.id })
        }}
        onNodeDrag={() => {
          if (!simulationRunning) {
            onSimulationToggle(true)
          }
        }}
        onNodeDragEnd={(node) => {
          // Soft pinning: moved nodes become pinned automatically
          node.fx = node.x
          node.fy = node.y
          
          pinnedHistoryRef.current.push(node.id)
          
          if (layout.pinLimit !== undefined && layout.pinLimit > 0) {
            while (pinnedHistoryRef.current.length > layout.pinLimit) {
              const oldestId = pinnedHistoryRef.current.shift()
              if (oldestId && !pinnedHistoryRef.current.includes(oldestId)) {
                const oldestNode = graph.nodes.find(n => n.id === oldestId) as any
                if (oldestNode) {
                  delete oldestNode.fx
                  delete oldestNode.fy
                }
                onContextAction('node', oldestId, 'unpin')
              }
            }
          }

          onContextAction('node', node.id, 'pin')

          if (!simulationRunning) {
            onSimulationToggle(true)
          }
          fgRef.current?.d3ReheatSimulation()
        }}
        onLinkClick={(edge) => onEdgeClick(edge)}
        onLinkRightClick={(edge, event) => {
          event.preventDefault()
          setContextMenu({ x: event.clientX, y: event.clientY, kind: 'edge', id: edge.id })
        }}
        onBackgroundClick={() => {
          onBackgroundClick()
          closeContextMenu()
        }}
      />

      {contextMenu ? (
        <div 
          className="fixed z-50 flex flex-col gap-1 min-w-[160px] p-1.5 bg-card/95 backdrop-blur border rounded-lg shadow-2xl animate-in fade-in zoom-in-95"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {activeContextMenuItems.map((item) => (
            <Button
              key={`${contextMenu.kind}-${item.action}`}
              variant="ghost"
              size="sm"
              className="justify-start h-8 px-2 text-xs font-medium"
              onClick={() => {
                if (contextMenu.kind === 'node') {
                  if (item.action === 'unpin') {
                    const internalNode = graph.nodes.find(n => n.id === contextMenu.id) as any
                    if (internalNode) {
                      delete internalNode.fx
                      delete internalNode.fy
                      fgRef.current?.d3ReheatSimulation()
                    }
                  }
                  onContextAction('node', contextMenu.id, item.action as GraphNodeContextAction)
                } else {
                  onContextAction('edge', contextMenu.id, item.action as GraphEdgeContextAction)
                }
                closeContextMenu()
              }}
            >
              {item.label}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
