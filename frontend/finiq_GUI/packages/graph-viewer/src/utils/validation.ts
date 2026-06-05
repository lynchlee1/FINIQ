import type {
  GraphData,
  GraphEdge,
  GraphNode,
  InputEdge,
  InputNode,
  ValidationIssue,
  ValidationResult,
} from '../types/graph'

function isObjectLike(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toSafeNode(raw: InputNode, index: number, issues: ValidationIssue[]): GraphNode {
  const tags = Array.isArray(raw.tags)
    ? raw.tags.filter((tag) => typeof tag === 'string').map((tag) => tag.trim()).filter(Boolean)
    : []

  const properties =
    raw.properties && isObjectLike(raw.properties) ? raw.properties : {}

  if (raw.properties !== undefined && !isObjectLike(raw.properties)) {
    issues.push({
      level: 'warning',
      path: `nodes[${index}].properties`,
      message: 'Node properties should be an object. Using empty object.',
    })
  }

  const riskLevel = (typeof (raw as any).riskLevel === 'string' && ['low', 'medium', 'high'].includes((raw as any).riskLevel))
    ? (raw as any).riskLevel as 'low' | 'medium' | 'high'
    : undefined

  return {
    id: raw.id.trim(),
    label: raw.label?.trim() || raw.id.trim(),
    type: raw.type?.trim() || 'default',
    group: raw.group?.trim() || undefined,
    tags,
    properties,
    riskLevel,
    riskDescription: (raw as any).riskDescription,
  }
}

function edgeKey(source: string, target: string, relation: string, directed: boolean): string {
  if (directed) {
    return `d|${source}|${target}|${relation}`
  }
  const [a, b] = source <= target ? [source, target] : [target, source]
  return `u|${a}|${b}|${relation}`
}

function toSafeEdge(raw: InputEdge, index: number, issues: ValidationIssue[]): GraphEdge {
  const weight =
    raw.weight === undefined
      ? 1
      : typeof raw.weight === 'number' && Number.isFinite(raw.weight) && raw.weight > 0
        ? raw.weight
        : Number.NaN

  if (Number.isNaN(weight)) {
    issues.push({
      level: 'error',
      path: `edges[${index}].weight`,
      message: 'Edge weight must be a finite number greater than 0.',
    })
  }

  const properties =
    raw.properties && isObjectLike(raw.properties) ? raw.properties : {}

  if (raw.properties !== undefined && !isObjectLike(raw.properties)) {
    issues.push({
      level: 'warning',
      path: `edges[${index}].properties`,
      message: 'Edge properties should be an object. Using empty object.',
    })
  }

  const category = (raw.category && ['equity', 'personnel', 'address', 'transaction', 'other'].includes(raw.category))
    ? raw.category
    : 'other'

  return {
    id: raw.id?.trim() || `e-${index + 1}`,
    source: raw.source.trim(),
    target: raw.target.trim(),
    relation: raw.relation.trim() || 'related',
    category,
    weight,
    directed: Boolean(raw.directed),
    properties,
  }
}

export function parseAndValidateGraphJson(rawText: string): ValidationResult {
  const issues: ValidationIssue[] = []
  const emptyGraph: GraphData = { nodes: [], edges: [] }

  if (!rawText.trim()) {
    return {
      graph: emptyGraph,
      issues: [{ level: 'error', message: 'Input is empty. Paste or upload valid JSON.' }],
      hasErrors: true,
    }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(rawText)
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Unknown parse error.'
    return {
      graph: emptyGraph,
      issues: [{ level: 'error', message: `Malformed JSON: ${msg}` }],
      hasErrors: true,
    }
  }

  if (!isObjectLike(parsed)) {
    return {
      graph: emptyGraph,
      issues: [{ level: 'error', message: 'JSON root must be an object with nodes and edges arrays.' }],
      hasErrors: true,
    }
  }

  const rawNodes = parsed.nodes
  const rawEdges = parsed.edges

  if (!Array.isArray(rawNodes) || !Array.isArray(rawEdges)) {
    return {
      graph: emptyGraph,
      issues: [{ level: 'error', message: 'Expected { nodes: [...], edges: [...] }.' }],
      hasErrors: true,
    }
  }

  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  const nodeIds = new Set<string>()

  rawNodes.forEach((value, index) => {
    if (!isObjectLike(value)) {
      issues.push({
        level: 'error',
        path: `nodes[${index}]`,
        message: 'Node entry must be an object.',
      })
      return
    }

    const raw = value as Partial<InputNode>
    if (typeof raw.id !== 'string' || !raw.id.trim()) {
      issues.push({
        level: 'error',
        path: `nodes[${index}].id`,
        message: 'Node id must be a non-empty string.',
      })
      return
    }

    if (typeof raw.label !== 'string' || !raw.label.trim()) {
      issues.push({
        level: 'warning',
        path: `nodes[${index}].label`,
        message: `Node "${raw.id}" has empty label. Falling back to id.`,
      })
    }

    if (typeof raw.type !== 'string' || !raw.type.trim()) {
      issues.push({
        level: 'warning',
        path: `nodes[${index}].type`,
        message: `Node "${raw.id}" has empty type. Falling back to "default".`,
      })
    }

    if (nodeIds.has(raw.id.trim())) {
      issues.push({
        level: 'error',
        path: `nodes[${index}].id`,
        message: `Duplicate node id "${raw.id.trim()}".`,
      })
      return
    }

    const node = toSafeNode(raw as InputNode, index, issues)
    nodes.push(node)
    nodeIds.add(node.id)
  })

  const edgeIds = new Set<string>()
  const duplicateEdgeTracker = new Map<string, number>()

  rawEdges.forEach((value, index) => {
    if (!isObjectLike(value)) {
      issues.push({
        level: 'error',
        path: `edges[${index}]`,
        message: 'Edge entry must be an object.',
      })
      return
    }

    const raw = value as Partial<InputEdge>
    if (typeof raw.source !== 'string' || !raw.source.trim()) {
      issues.push({
        level: 'error',
        path: `edges[${index}].source`,
        message: 'Edge source must be a non-empty string.',
      })
      return
    }
    if (typeof raw.target !== 'string' || !raw.target.trim()) {
      issues.push({
        level: 'error',
        path: `edges[${index}].target`,
        message: 'Edge target must be a non-empty string.',
      })
      return
    }
    if (typeof raw.relation !== 'string' || !raw.relation.trim()) {
      issues.push({
        level: 'warning',
        path: `edges[${index}].relation`,
        message: 'Edge relation is empty. Falling back to "related".',
      })
    }

    const edge = toSafeEdge(raw as InputEdge, index, issues)

    if (edgeIds.has(edge.id)) {
      issues.push({
        level: 'error',
        path: `edges[${index}].id`,
        message: `Duplicate edge id "${edge.id}".`,
      })
      return
    }

    if (!nodeIds.has(String(edge.source))) {
      issues.push({
        level: 'error',
        path: `edges[${index}].source`,
        message: `Edge source "${String(edge.source)}" does not match any node id.`,
      })
    }
    if (!nodeIds.has(String(edge.target))) {
      issues.push({
        level: 'error',
        path: `edges[${index}].target`,
        message: `Edge target "${String(edge.target)}" does not match any node id.`,
      })
    }

    if (String(edge.source) === String(edge.target)) {
      issues.push({
        level: 'warning',
        path: `edges[${index}]`,
        message: `Self-loop detected on node "${String(edge.source)}".`,
      })
    }

    const key = edgeKey(String(edge.source), String(edge.target), edge.relation, edge.directed)
    const count = (duplicateEdgeTracker.get(key) ?? 0) + 1
    duplicateEdgeTracker.set(key, count)
    if (count > 1) {
      issues.push({
        level: 'warning',
        path: `edges[${index}]`,
        message: `Duplicate edge detected (${String(edge.source)} -> ${String(edge.target)}, relation "${edge.relation}").`,
      })
    }

    edgeIds.add(edge.id)
    edges.push(edge)
  })

  const hasErrors = issues.some((issue) => issue.level === 'error')
  return { graph: { nodes, edges }, issues, hasErrors }
}

export const SAMPLE_GRAPH_JSON = JSON.stringify(
  {
    nodes: [
      { id: 'samsung-elec', label: 'Samsung Electronics', type: 'Company', group: 'Samsung Group', riskLevel: 'low' },
      { id: 'samsung-c-t', label: 'Samsung C&T', type: 'Company', group: 'Samsung Group', riskLevel: 'low' },
      { id: 'lee-jae-yong', label: 'Lee Jae-yong', type: 'Person', group: 'Owner', tags: ['Executive'] },
      { id: 'paper-co-1', label: 'Alpha Holdings', type: 'Company', riskLevel: 'high', riskDescription: 'Shared address with 20 other entities.' },
      { id: 'address-123', label: '123 Seocho-daero', type: 'Address' },
    ],
    edges: [
      { source: 'lee-jae-yong', target: 'samsung-elec', relation: 'Chairman', category: 'personnel', directed: true },
      { source: 'lee-jae-yong', target: 'samsung-c-t', relation: 'Largest Shareholder', category: 'equity', directed: true, weight: 17.97 },
      { source: 'samsung-c-t', target: 'samsung-elec', relation: 'Subsidiary', category: 'equity', directed: true, weight: 5.01 },
      { source: 'paper-co-1', target: 'address-123', relation: 'Registered Address', category: 'address', directed: true },
    ],
  },
  null,
  2,
)
