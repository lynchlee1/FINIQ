import type { FilterState, GraphData, GraphEdge, GraphNode } from '../types/graph'
import { calculateDegrees, nHopNeighborhood } from './algorithms'

function toNodeId(value: string | GraphNode): string {
  return typeof value === 'string' ? value : value.id
}

function safeString(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

function recordContains(record: Record<string, unknown>, queryLower: string): boolean {
  return Object.entries(record).some(([key, value]) => {
    const content = `${key}:${safeString(value)}`.toLowerCase()
    return content.includes(queryLower)
  })
}

function nodeMatchesQuery(node: GraphNode, queryLower: string): boolean {
  return (
    node.id.toLowerCase().includes(queryLower) ||
    node.label.toLowerCase().includes(queryLower) ||
    node.type.toLowerCase().includes(queryLower) ||
    safeString(node.group).toLowerCase().includes(queryLower) ||
    node.tags.some((tag) => tag.toLowerCase().includes(queryLower)) ||
    recordContains(node.properties, queryLower)
  )
}

function edgeMatchesQuery(edge: GraphEdge, queryLower: string): boolean {
  return (
    edge.relation.toLowerCase().includes(queryLower) ||
    recordContains(edge.properties, queryLower)
  )
}

function criterionCount(filters: FilterState): number {
  return [
    filters.nodeTypes.length > 0,
    filters.groups.length > 0,
    filters.tags.length > 0,
    filters.edgeRelations.length > 0,
    filters.minWeight > 0,
    filters.minDegree > 0,
    filters.direction !== 'all',
  ].filter(Boolean).length
}

function nodeFilterChecks(node: GraphNode, filters: FilterState, degree: number): boolean[] {
  const checks: boolean[] = []
  if (filters.nodeTypes.length > 0) {
    checks.push(filters.nodeTypes.includes(node.type))
  }
  if (filters.groups.length > 0) {
    checks.push(filters.groups.includes(node.group ?? ''))
  }
  if (filters.tags.length > 0) {
    checks.push(filters.tags.some((tag) => node.tags.includes(tag)))
  }
  if (filters.minDegree > 0) {
    checks.push(degree >= filters.minDegree)
  }
  return checks
}

function edgeFilterChecks(edge: GraphEdge, filters: FilterState): boolean[] {
  const checks: boolean[] = []
  if (filters.edgeRelations.length > 0) {
    checks.push(filters.edgeRelations.includes(edge.relation))
  }
  if (filters.minWeight > 0) {
    checks.push(edge.weight >= filters.minWeight)
  }
  if (filters.direction !== 'all') {
    checks.push(filters.direction === 'directed' ? edge.directed : !edge.directed)
  }
  return checks
}

function evaluate(checks: boolean[], logic: FilterState['logic']): boolean {
  if (checks.length === 0) {
    return true
  }
  return logic === 'AND' ? checks.every(Boolean) : checks.some(Boolean)
}

export interface VisibleGraphResult {
  graph: GraphData
  degreeMap: Map<string, number>
  visibleNodeIds: Set<string>
  visibleEdgeIds: Set<string>
}

export function computeVisibleGraph(params: {
  graph: GraphData
  filters: FilterState
  hiddenNodeIds: Set<string>
  hiddenEdgeIds: Set<string>
  searchQuery: string
  neighborhoodRootId?: string
  neighborhoodHops: number
}): VisibleGraphResult {
  const { graph, filters, hiddenNodeIds, hiddenEdgeIds, searchQuery, neighborhoodRootId, neighborhoodHops } =
    params

  const degreeMap = calculateDegrees(graph)
  const hasAnyFilter = criterionCount(filters) > 0
  const queryLower = searchQuery.trim().toLowerCase()
  const neighborhood =
    neighborhoodRootId && neighborhoodHops > 0
      ? nHopNeighborhood(graph, neighborhoodRootId, neighborhoodHops)
      : undefined

  const visibleNodeIds = new Set<string>()
  graph.nodes.forEach((node) => {
    if (hiddenNodeIds.has(node.id)) {
      return
    }
    const degree = degreeMap.get(node.id) ?? 0
    const nodeChecks = nodeFilterChecks(node, filters, degree)
    const nodeFilterPass = evaluate(nodeChecks, filters.logic)
    const queryPass = queryLower ? nodeMatchesQuery(node, queryLower) : true
    const neighborhoodPass = neighborhood ? neighborhood.has(node.id) : true
    const shouldShow = hasAnyFilter ? nodeFilterPass && queryPass && neighborhoodPass : queryPass && neighborhoodPass
    if (shouldShow) {
      visibleNodeIds.add(node.id)
    }
  })

  const visibleEdgeIds = new Set<string>()
  const visibleEdges = graph.edges.filter((edge) => {
    if (hiddenEdgeIds.has(edge.id)) {
      return false
    }

    const sourceId = toNodeId(edge.source)
    const targetId = toNodeId(edge.target)
    const endpointsVisible = visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId)
    if (!endpointsVisible) {
      return false
    }

    const edgeChecks = edgeFilterChecks(edge, filters)
    const edgeFilterPass = evaluate(edgeChecks, filters.logic)
    const queryPass = queryLower ? edgeMatchesQuery(edge, queryLower) || endpointsVisible : true
    const shouldShow = hasAnyFilter ? edgeFilterPass && queryPass : queryPass

    if (shouldShow) {
      visibleEdgeIds.add(edge.id)
      return true
    }
    return false
  })

  if (filters.hideIsolated) {
    const connected = new Set<string>()
    visibleEdges.forEach((edge) => {
      connected.add(toNodeId(edge.source))
      connected.add(toNodeId(edge.target))
    })
    Array.from(visibleNodeIds).forEach((id) => {
      if (!connected.has(id)) {
        visibleNodeIds.delete(id)
      }
    })
  }

  const nodes = graph.nodes.filter((node) => visibleNodeIds.has(node.id))
  const edges = visibleEdges.filter((edge) => {
    const sourceId = toNodeId(edge.source)
    const targetId = toNodeId(edge.target)
    return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId)
  })

  return {
    graph: { nodes, edges },
    degreeMap,
    visibleNodeIds,
    visibleEdgeIds,
  }
}
