import type { GraphData, GraphEdge, GraphNode } from '../types/graph'

function nodeIdOf(nodeOrId: string | GraphNode): string {
  return typeof nodeOrId === 'string' ? nodeOrId : nodeOrId.id
}

export function buildAdjacency(graph: GraphData): Map<string, Set<string>> {
  const adjacency = new Map<string, Set<string>>()
  graph.nodes.forEach((node) => adjacency.set(node.id, new Set()))
  graph.edges.forEach((edge) => {
    const source = nodeIdOf(edge.source)
    const target = nodeIdOf(edge.target)
    adjacency.get(source)?.add(target)
    adjacency.get(target)?.add(source)
  })
  return adjacency
}

export function calculateDegrees(graph: GraphData): Map<string, number> {
  const degrees = new Map<string, number>()
  graph.nodes.forEach((node) => degrees.set(node.id, 0))
  graph.edges.forEach((edge) => {
    const source = nodeIdOf(edge.source)
    const target = nodeIdOf(edge.target)
    degrees.set(source, (degrees.get(source) ?? 0) + 1)
    if (source !== target) {
      degrees.set(target, (degrees.get(target) ?? 0) + 1)
    }
  })
  return degrees
}

export function nHopNeighborhood(graph: GraphData, rootId: string, hops: number): Set<string> {
  if (!rootId) {
    return new Set()
  }
  const adjacency = buildAdjacency(graph)
  const visited = new Set<string>([rootId])
  let frontier = new Set<string>([rootId])

  for (let hop = 0; hop < hops; hop += 1) {
    const next = new Set<string>()
    frontier.forEach((nodeId) => {
      adjacency.get(nodeId)?.forEach((neighbor) => {
        if (!visited.has(neighbor)) {
          visited.add(neighbor)
          next.add(neighbor)
        }
      })
    })
    frontier = next
    if (frontier.size === 0) {
      break
    }
  }

  return visited
}

export function shortestPath(graph: GraphData, fromId: string, toId: string): string[] {
  if (!fromId || !toId || fromId === toId) {
    return fromId && toId ? [fromId] : []
  }

  const adjacency = buildAdjacency(graph)
  const queue: string[] = [fromId]
  const visited = new Set<string>([fromId])
  const prev = new Map<string, string>()

  while (queue.length > 0) {
    const current = queue.shift() as string
    if (current === toId) {
      break
    }
    adjacency.get(current)?.forEach((neighbor) => {
      if (visited.has(neighbor)) {
        return
      }
      visited.add(neighbor)
      prev.set(neighbor, current)
      queue.push(neighbor)
    })
  }

  if (!visited.has(toId)) {
    return []
  }

  const path: string[] = []
  let cursor: string | undefined = toId
  while (cursor) {
    path.push(cursor)
    cursor = prev.get(cursor)
  }
  return path.reverse()
}

export function connectedNodeAndEdgeSets(graph: GraphData, nodeId: string): {
  nodeSet: Set<string>
  edgeSet: Set<string>
} {
  const nodeSet = new Set<string>()
  const edgeSet = new Set<string>()
  nodeSet.add(nodeId)

  graph.edges.forEach((edge) => {
    const source = nodeIdOf(edge.source)
    const target = nodeIdOf(edge.target)
    if (source === nodeId || target === nodeId) {
      edgeSet.add(edge.id)
      nodeSet.add(source)
      nodeSet.add(target)
    }
  })

  return { nodeSet, edgeSet }
}

export function withCurvedDuplicateLinks(graph: GraphData): GraphData {
  const pairToEdgeIds = new Map<string, string[]>()
  const edgesById = new Map<string, GraphEdge>()

  graph.edges.forEach((edge) => {
    const source = nodeIdOf(edge.source)
    const target = nodeIdOf(edge.target)
    const relation = edge.relation
    const pairKey =
      source <= target
        ? `${source}::${target}::${relation}`
        : `${target}::${source}::${relation}`

    if (!pairToEdgeIds.has(pairKey)) {
      pairToEdgeIds.set(pairKey, [])
    }
    pairToEdgeIds.get(pairKey)?.push(edge.id)
    edgesById.set(edge.id, edge)
  })

  const edges = graph.edges.map((edge) => {
    const source = nodeIdOf(edge.source)
    const target = nodeIdOf(edge.target)
    if (source === target) {
      return { ...edge, curvature: 0.55 }
    }

    const relation = edge.relation
    const pairKey =
      source <= target
        ? `${source}::${target}::${relation}`
        : `${target}::${source}::${relation}`

    const grouped = pairToEdgeIds.get(pairKey) ?? []
    if (grouped.length <= 1) {
      return { ...edge, curvature: 0 }
    }

    const idx = grouped.indexOf(edge.id)
    const center = (grouped.length - 1) / 2
    const curvature = (idx - center) * 0.18
    return { ...edge, curvature }
  })

  return { nodes: graph.nodes, edges }
}

export function analyzeNetworkRisks(graph: GraphData): Map<string, { level: 'low' | 'medium' | 'high'; description: string }> {
  const risks = new Map<string, { level: 'low' | 'medium' | 'high'; description: string }>()
  const degrees = calculateDegrees(graph)

  // 1. Paper Company Detection: High degree of shared addresses/properties but low equity/personnel connectivity
  graph.nodes.forEach((node) => {
    const connectedEdges = graph.edges.filter(
      (e) => nodeIdOf(e.source) === node.id || nodeIdOf(e.target) === node.id,
    )
    const categories = new Set(connectedEdges.map((e) => e.category))

    if (categories.has('address') && connectedEdges.length > 5 && categories.size === 1) {
      risks.set(node.id, {
        level: 'high',
        description: 'Potential shell/paper company: High volume of shared address links with no other relationship types.',
      })
    }

    // 2. Interlocking Directorates: Person connected to many companies
    if (node.type === 'Person' && (degrees.get(node.id) ?? 0) > 3) {
      risks.set(node.id, {
        level: 'medium',
        description: `Interlocking directorate: Connected to ${(degrees.get(node.id) ?? 0)} different entities.`,
      })
    }
  })

  return risks
}

export function detectSharedPropertyLinks(
  nodes: GraphNode[],
  propertyKeys: string[] = ['address', 'phone', 'email'],
): GraphEdge[] {
  const propertyToNodeIds = new Map<string, string[]>()

  nodes.forEach((node) => {
    propertyKeys.forEach((key) => {
      const value = node.properties[key]
      if (typeof value === 'string' && value.trim()) {
        const normalizedValue = `${key}:${value.trim().toLowerCase()}`
        if (!propertyToNodeIds.has(normalizedValue)) {
          propertyToNodeIds.set(normalizedValue, [])
        }
        propertyToNodeIds.get(normalizedValue)?.push(node.id)
      }
    })
  })

  const newEdges: GraphEdge[] = []
  propertyToNodeIds.forEach((nodeIds, prop) => {
    if (nodeIds.length < 2) {
      return
    }

    // Create a mesh of connections for nodes sharing the same property
    for (let i = 0; i < nodeIds.length; i++) {
      for (let j = i + 1; j < nodeIds.length; j++) {
        const [source, target] = [nodeIds[i], nodeIds[j]]
        const propName = prop.split(':')[0]
        const propValue = prop.split(':').slice(1).join(':')

        newEdges.push({
          id: `shared-${propName}-${source}-${target}`,
          source,
          target,
          relation: `Shared ${propName}`,
          category: 'address',
          weight: 1,
          directed: false,
          properties: { [propName]: propValue },
        })
      }
    }
  })

  return newEdges
}
