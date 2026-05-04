export type JsonMap = Record<string, unknown>

export interface InputNode {
  id: string
  label: string
  type: string
  group?: string
  tags?: string[]
  properties?: JsonMap
}

export interface InputEdge {
  id?: string
  source: string
  target: string
  relation: string
  weight?: number
  directed?: boolean
  properties?: JsonMap
}

export interface GraphNode {
  id: string
  label: string
  type: string
  group?: string
  tags: string[]
  properties: JsonMap
  hidden?: boolean
  pinned?: boolean
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number
  fy?: number
}

export interface GraphEdge {
  id: string
  source: string | GraphNode
  target: string | GraphNode
  relation: string
  weight: number
  directed: boolean
  properties: JsonMap
  hidden?: boolean
  curvature?: number
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ValidationIssue {
  level: 'error' | 'warning'
  message: string
  path?: string
}

export interface ValidationResult {
  graph: GraphData
  issues: ValidationIssue[]
  hasErrors: boolean
}

export interface FilterState {
  nodeTypes: string[]
  groups: string[]
  tags: string[]
  edgeRelations: string[]
  minWeight: number
  minDegree: number
  direction: 'all' | 'directed' | 'undirected'
  logic: 'AND' | 'OR'
  hideIsolated: boolean
}

export interface StyleRule {
  id: string
  target: 'node' | 'edge'
  field: 'type' | 'group' | 'tag' | 'relation' | 'weight' | 'degree'
  operator: 'equals' | 'contains' | 'gte' | 'lte' | 'between'
  value: string
  value2?: string
  color: string
  size?: number
}

export type NodeShape = 'circle' | 'square' | 'diamond' | 'triangle'

export interface NodeTypeStyle {
  color: string
  size: number
  shape: NodeShape
  borderColor: string
  borderWidth: number
}

export interface GraphStyleConfig {
  presetName: string
  backgroundColor: string
  nodeColor: string
  nodeSize: number
  nodeOpacity: number
  nodeBorderColor: string
  nodeBorderWidth: number
  edgeColor: string
  edgeWidth: number
  edgeOpacity: number
  arrowVisibility: boolean
  labelVisible: boolean
  labelFontSize: number
  maxLabelLength: number
  labelVisibilityZoom: number
  hoverColor: string
  selectedColor: string
  highlightedColor: string
  nodeTypeStyles: Record<string, NodeTypeStyle>
  styleRules: StyleRule[]
}

export interface LayoutConfig {
  linkDistance: number
  chargeStrength: number
  collisionRadius: number
  alphaDecay: number
  preservePinnedNodes: boolean
  autoLayoutAfterFilter: boolean
}

export interface GraphSnapshot {
  nodes: GraphNode[]
  edges: GraphEdge[]
}
