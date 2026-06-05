import { useCallback, useMemo, useState } from 'react'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useUndoableGraph } from '../hooks/useUndoableGraph'
import type {
  FilterState,
  GraphData,
  GraphEdge,
  GraphNode,
  GraphStyleConfig,
  LayoutConfig,
  ValidationResult,
} from '../types/graph'
import {
  analyzeNetworkRisks,
  connectedNodeAndEdgeSets,
  detectSharedPropertyLinks,
  withCurvedDuplicateLinks,
} from '../utils/algorithms'
import { computeVisibleGraph } from '../utils/filtering'
import { DEFAULT_STYLE, STYLE_PRESETS } from '../utils/stylePresets'
import { parseAndValidateGraphJson, SAMPLE_GRAPH_JSON } from '../utils/validation'

export type GraphViewerTheme = 'light' | 'dark'
export type GraphContextActionKind = 'node' | 'edge'
export type GraphNodeContextAction = 'hide' | 'delete' | 'pin' | 'unpin' | 'neighbors'
export type GraphEdgeContextAction = 'hide' | 'delete'
export type GraphContextAction = GraphNodeContextAction | GraphEdgeContextAction

export interface GraphContextActionHandler {
  (kind: 'node', id: string, action: GraphNodeContextAction): void
  (kind: 'edge', id: string, action: GraphEdgeContextAction): void
}

export const EMPTY_GRAPH: GraphData = { nodes: [], edges: [] }

export const DEFAULT_FILTERS: FilterState = {
  nodeTypes: [],
  groups: [],
  tags: [],
  edgeRelations: [],
  edgeCategories: [],
  minWeight: 0,
  minDegree: 0,
  direction: 'all',
  logic: 'AND',
  hideIsolated: false,
}

export const DEFAULT_LAYOUT: LayoutConfig = {
  linkDistance: 80,
  chargeStrength: -180,
  collisionRadius: 10,
  alphaDecay: 0.0228,
  preservePinnedNodes: true,
  autoLayoutAfterFilter: true,
}

const DEFAULT_THEME_PRESETS: Record<GraphViewerTheme, string> = {
  light: 'Default',
  dark: 'AI Studio',
}

export interface UseGraphViewerOptions {
  initialTheme?: GraphViewerTheme
  initialGraphJson?: string
  initialStyle?: GraphStyleConfig
  initialStylePresets?: Record<string, GraphStyleConfig>
  initialLayout?: LayoutConfig
  initialFilters?: FilterState
  searchDebounceMs?: number
  neighborhoodHops?: number
  themePresetNames?: Partial<Record<GraphViewerTheme, string>>
}

export interface GraphViewerController {
  appTheme: GraphViewerTheme
  importText: string
  stylePresets: Record<string, GraphStyleConfig>
  style: GraphStyleConfig
  layout: LayoutConfig
  filters: FilterState
  searchText: string
  simulationRunning: boolean
  graph: GraphData
  visibleGraph: GraphData
  visibleDegreeMap: Map<string, number>
  selectedNodeIds: Set<string>
  selectedEdgeIds: Set<string>
  highlightedNodeIds: Set<string>
  highlightedEdgeIds: Set<string>
  nodeTypes: string[]
  performanceWarning: boolean
  canUndo: boolean
  canRedo: boolean
  setImportText: (value: string) => void
  setStyle: (next: GraphStyleConfig) => void
  setSimulationRunning: (running: boolean) => void
  setSearchText: (value: string) => void
  setGraph: (updater: (current: GraphData) => GraphData) => void
  replaceGraph: (graph: GraphData) => void
  toggleTheme: () => void
  undo: () => void
  redo: () => void
  importGraph: (jsonText: string) => ValidationResult
  importFromFile: (file: File) => Promise<ValidationResult>
  updateFilters: (next: FilterState) => void
  updateLayout: (next: LayoutConfig) => void
  applyPreset: (presetName: string) => void
  addPreset: (presetName: string) => void
  removePreset: (presetName: string) => void
  savePreset: (presetName: string) => void
  onNodeClick: (node: GraphNode, multiSelect: boolean) => void
  onEdgeClick: (edge: GraphEdge) => void
  onBackgroundClick: () => void
  onNodeHover: (node: GraphNode | null) => void
  onContextAction: GraphContextActionHandler
  onVisibleBounds: (width: number, height: number) => void
  runCorporateAnalysis: () => void
}

function cloneStyle(style: GraphStyleConfig): GraphStyleConfig {
  return {
    ...style,
    nodeTypeStyles: { ...style.nodeTypeStyles },
    styleRules: style.styleRules.map((rule) => ({ ...rule })),
  }
}

function cloneStylePresets(presets: Record<string, GraphStyleConfig>): Record<string, GraphStyleConfig> {
  return Object.fromEntries(
    Object.entries(presets).map(([name, style]) => [name, cloneStyle(style)]),
  )
}

function applyThemeColors(style: GraphStyleConfig, themeStyle: GraphStyleConfig): GraphStyleConfig {
  return {
    ...style,
    presetName: themeStyle.presetName,
    backgroundColor: themeStyle.backgroundColor,
    nodeColor: themeStyle.nodeColor,
    nodeBorderColor: themeStyle.nodeBorderColor,
    edgeColor: themeStyle.edgeColor,
    hoverColor: themeStyle.hoverColor,
    selectedColor: themeStyle.selectedColor,
    highlightedColor: themeStyle.highlightedColor,
  }
}

function normalizeEdgeIds(graph: GraphData): GraphData {
  const ids = new Set<string>()
  return {
    nodes: graph.nodes.map((node) => ({ ...node })),
    edges: graph.edges.map((edge, index) => {
      let id = edge.id
      if (!id || ids.has(id)) {
        id = `e-${index + 1}-${crypto.randomUUID().slice(0, 6)}`
      }
      ids.add(id)
      return { ...edge, id }
    }),
  }
}

function toNodeId(value: string | GraphNode): string {
  return typeof value === 'string' ? value : value.id
}

function resolveThemePreset(
  theme: GraphViewerTheme,
  presets: Record<string, GraphStyleConfig>,
  themePresetNames: Record<GraphViewerTheme, string>,
): GraphStyleConfig {
  const preferred = presets[themePresetNames[theme]]
  if (preferred) {
    return preferred
  }
  const fallback = presets.Default ?? presets['AI Studio']
  if (fallback) {
    return fallback
  }
  return cloneStyle(DEFAULT_STYLE)
}

export function useGraphViewer(options: UseGraphViewerOptions = {}): GraphViewerController {
  const [appTheme, setAppTheme] = useState<GraphViewerTheme>(options.initialTheme ?? 'light')
  const [importText, setImportText] = useState<string>('')
  const [stylePresets, setStylePresets] = useState<Record<string, GraphStyleConfig>>(() =>
    cloneStylePresets(options.initialStylePresets ?? STYLE_PRESETS),
  )
  const [style, setStyle] = useState<GraphStyleConfig>(() => cloneStyle(options.initialStyle ?? DEFAULT_STYLE))
  const [layout, setLayout] = useState<LayoutConfig>(options.initialLayout ?? DEFAULT_LAYOUT)
  const [filters, setFilters] = useState<FilterState>(options.initialFilters ?? DEFAULT_FILTERS)
  const [searchText, setSearchText] = useState('')
  const [simulationRunning, setSimulationRunning] = useState(false)
  const [hiddenNodeIds, setHiddenNodeIds] = useState<Set<string>>(new Set())
  const [hiddenEdgeIds, setHiddenEdgeIds] = useState<Set<string>>(new Set())
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(new Set())
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<Set<string>>(new Set())
  const [hoverNodeId, setHoverNodeId] = useState<string | undefined>(undefined)
  const [neighborhoodRootId, setNeighborhoodRootId] = useState<string | undefined>(undefined)
  const [initialGraph] = useState<GraphData>(() => {
    const source = options.initialGraphJson ?? SAMPLE_GRAPH_JSON
    const parsed = parseAndValidateGraphJson(source)
    return parsed.hasErrors ? EMPTY_GRAPH : normalizeEdgeIds(parsed.graph)
  })

  const neighborhoodHops = options.neighborhoodHops ?? 1
  const themePresetNames = useMemo<Record<GraphViewerTheme, string>>(
    () => ({
      ...DEFAULT_THEME_PRESETS,
      ...options.themePresetNames,
    }),
    [options.themePresetNames],
  )
  const debouncedSearch = useDebouncedValue(searchText, options.searchDebounceMs ?? 200)
  const { graph, setGraph, replaceGraph, undo, redo, canUndo, canRedo } = useUndoableGraph(initialGraph)

  const clearTransientState = useCallback(() => {
    setHiddenNodeIds(new Set())
    setHiddenEdgeIds(new Set())
    setSelectedNodeIds(new Set())
    setSelectedEdgeIds(new Set())
    setNeighborhoodRootId(undefined)
  }, [])

  const importGraph = useCallback(
    (jsonText: string): ValidationResult => {
      const result = parseAndValidateGraphJson(jsonText)
      if (result.hasErrors) {
        return result
      }
      replaceGraph(normalizeEdgeIds(result.graph))
      clearTransientState()
      return result
    },
    [clearTransientState, replaceGraph],
  )

  const importFromFile = useCallback(
    (file: File): Promise<ValidationResult> =>
      new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => {
          const text = typeof reader.result === 'string' ? reader.result : ''
          setImportText(text)
          resolve(importGraph(text))
        }
        reader.onerror = () => {
          reject(reader.error ?? new Error(`Failed to read file "${file.name}".`))
        }
        reader.readAsText(file)
      }),
    [importGraph],
  )

  const visibleResult = useMemo(
    () =>
      computeVisibleGraph({
        graph,
        filters,
        hiddenNodeIds,
        hiddenEdgeIds,
        searchQuery: debouncedSearch,
        neighborhoodRootId,
        neighborhoodHops,
      }),
    [graph, filters, hiddenNodeIds, hiddenEdgeIds, debouncedSearch, neighborhoodRootId, neighborhoodHops],
  )

  const visibleGraph = useMemo(
    () => withCurvedDuplicateLinks(visibleResult.graph),
    [visibleResult.graph],
  )

  const highlighted = useMemo(() => {
    const singleSelected = selectedNodeIds.size === 1 ? Array.from(selectedNodeIds)[0] : undefined
    const focusNode = hoverNodeId ?? singleSelected
    if (!focusNode) {
      return { nodeSet: new Set<string>(), edgeSet: new Set<string>() }
    }
    return connectedNodeAndEdgeSets(visibleGraph, focusNode)
  }, [hoverNodeId, selectedNodeIds, visibleGraph])

  const nodeTypes = useMemo(
    () => Array.from(new Set(graph.nodes.map((node) => node.type))).sort(),
    [graph.nodes],
  )

  const performanceWarning = graph.nodes.length >= 1000 || graph.edges.length >= 3000

  const toggleTheme = useCallback(() => {
    const nextTheme: GraphViewerTheme = appTheme === 'light' ? 'dark' : 'light'
    setAppTheme(nextTheme)
    const themePreset = resolveThemePreset(nextTheme, stylePresets, themePresetNames)
    setStyle((current) => applyThemeColors(current, themePreset))
  }, [appTheme, stylePresets, themePresetNames])

  const updateFilters = useCallback(
    (next: FilterState) => {
      setFilters(next)
      if (layout.autoLayoutAfterFilter) {
        setSimulationRunning(true)
      }
    },
    [layout.autoLayoutAfterFilter],
  )

  const updateLayout = useCallback(
    (next: LayoutConfig) => {
      const forceSettingsChanged =
        next.linkDistance !== layout.linkDistance ||
        next.chargeStrength !== layout.chargeStrength ||
        next.collisionRadius !== layout.collisionRadius ||
        next.alphaDecay !== layout.alphaDecay
      setLayout(next)
      if (forceSettingsChanged) {
        setSimulationRunning(true)
      }
    },
    [layout],
  )

  const applyPreset = useCallback(
    (presetName: string) => {
      const preset = stylePresets[presetName]
      if (preset) {
        setStyle(cloneStyle(preset))
      }
    },
    [stylePresets],
  )

  const addPreset = useCallback((presetName: string) => {
    const trimmed = presetName.trim()
    if (!trimmed) {
      return
    }
    setStylePresets((current) => {
      if (current[trimmed]) {
        return current
      }
      return {
        ...current,
        [trimmed]: cloneStyle({ ...style, presetName: trimmed }),
      }
    })
    setStyle((current) => ({ ...current, presetName: trimmed }))
  }, [style])

  const removePreset = useCallback(
    (presetName: string) => {
      setStylePresets((current) => {
        if (!current[presetName] || Object.keys(current).length <= 1) {
          return current
        }
        const next = { ...current }
        delete next[presetName]
        const fallbackName =
          next[themePresetNames[appTheme]]
            ? themePresetNames[appTheme]
            : Object.keys(next)[0]
        setStyle(cloneStyle(next[fallbackName]))
        return next
      })
    },
    [appTheme, themePresetNames],
  )

  const savePreset = useCallback(
    (presetName: string) => {
      setStylePresets((current) => {
        if (!current[presetName]) {
          return current
        }
        return {
          ...current,
          [presetName]: cloneStyle({ ...style, presetName }),
        }
      })
      setStyle((current) => ({ ...current, presetName }))
    },
    [style],
  )

  const onNodeClick = useCallback((node: GraphNode, multiSelect: boolean) => {
    const nodeId = node.id
    setSelectedEdgeIds(new Set())
    setSelectedNodeIds((prev) => {
      if (!multiSelect) {
        return new Set([nodeId])
      }
      const next = new Set(prev)
      if (next.has(nodeId)) {
        next.delete(nodeId)
      } else {
        next.add(nodeId)
      }
      return next
    })
  }, [])

  const onEdgeClick = useCallback((edge: GraphEdge) => {
    setSelectedNodeIds(new Set())
    setSelectedEdgeIds(new Set([edge.id]))
  }, [])

  const onBackgroundClick = useCallback(() => {
    setSelectedNodeIds(new Set())
    setSelectedEdgeIds(new Set())
  }, [])

  const onNodeHover = useCallback((node: GraphNode | null) => {
    const nextHoverNodeId = node?.id
    setHoverNodeId((current) => (current === nextHoverNodeId ? current : nextHoverNodeId))
  }, [])

  const onContextAction = useCallback(
    (kind: GraphContextActionKind, id: string, action: GraphContextAction) => {
      if (kind === 'node') {
        if (action === 'hide') {
          setHiddenNodeIds((prev) => new Set(prev).add(id))
        } else if (action === 'delete') {
          setGraph((current) => ({
            nodes: current.nodes.filter((n) => n.id !== id),
            edges: current.edges.filter((e) => toNodeId(e.source) !== id && toNodeId(e.target) !== id),
          }))
        } else if (action === 'pin' || action === 'unpin') {
          const pin = action === 'pin'
          setGraph((current) => ({
            nodes: current.nodes.map((node) =>
              node.id === id
                ? { ...node, pinned: pin, fx: pin ? node.x : undefined, fy: pin ? node.y : undefined }
                : node,
            ),
            edges: current.edges,
          }))
        } else if (action === 'neighbors') {
          setNeighborhoodRootId(id)
        }
      } else if (action === 'hide') {
        setHiddenEdgeIds((prev) => new Set(prev).add(id))
      } else if (action === 'delete') {
        setGraph((current) => ({
          nodes: current.nodes,
          edges: current.edges.filter((edge) => edge.id !== id),
        }))
      }
    },
    [setGraph],
  ) as GraphContextActionHandler

  const onVisibleBounds = useCallback(() => undefined, [])

  const runCorporateAnalysis = useCallback(() => {
    setGraph((current) => {
      // 1. Detect shared property links
      const sharedLinks = detectSharedPropertyLinks(current.nodes)
      
      // Filter out shared links that already exist as edges
      const existingKeys = new Set(current.edges.map(e => `${toNodeId(e.source)}|${toNodeId(e.target)}|${e.relation}`))
      const uniqueSharedLinks = sharedLinks.filter(e => !existingKeys.has(`${toNodeId(e.source)}|${toNodeId(e.target)}|${e.relation}`))

      const updatedGraph = {
        nodes: current.nodes,
        edges: [...current.edges, ...uniqueSharedLinks]
      }

      // 2. Analyze risks and update node properties
      const risks = analyzeNetworkRisks(updatedGraph)
      const nodesWithRisks = updatedGraph.nodes.map(node => {
        const risk = risks.get(node.id)
        if (risk) {
          return { ...node, riskLevel: risk.level, riskDescription: risk.description }
        }
        return node
      })

      return {
        nodes: nodesWithRisks,
        edges: updatedGraph.edges
      }
    })
  }, [setGraph])

  return {
    appTheme,
    importText,
    stylePresets,
    style,
    layout,
    filters,
    searchText,
    simulationRunning,
    graph,
    visibleGraph,
    visibleDegreeMap: visibleResult.degreeMap,
    selectedNodeIds,
    selectedEdgeIds,
    highlightedNodeIds: highlighted.nodeSet,
    highlightedEdgeIds: highlighted.edgeSet,
    nodeTypes,
    performanceWarning,
    canUndo,
    canRedo,
    setImportText,
    setStyle,
    setSimulationRunning,
    setSearchText,
    setGraph,
    replaceGraph,
    toggleTheme,
    undo,
    redo,
    importGraph,
    importFromFile,
    updateFilters,
    updateLayout,
    applyPreset,
    addPreset,
    removePreset,
    savePreset,
    onNodeClick,
    onEdgeClick,
    onBackgroundClick,
    onNodeHover,
    onContextAction,
    onVisibleBounds,
    runCorporateAnalysis,
  }
}

