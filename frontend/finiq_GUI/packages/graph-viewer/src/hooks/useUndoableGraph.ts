import { useMemo, useState, useCallback } from 'react'
import type { GraphData, GraphSnapshot } from '../types/graph'

function cloneGraph(graph: GraphData): GraphSnapshot {
  return {
    nodes: graph.nodes.map((node) => ({
      ...node,
      tags: [...node.tags],
      properties: { ...node.properties },
    })),
    edges: graph.edges.map((edge) => ({
      ...edge,
      source: typeof edge.source === 'string' ? edge.source : edge.source.id,
      target: typeof edge.target === 'string' ? edge.target : edge.target.id,
      properties: { ...edge.properties },
    })),
  }
}

export function useUndoableGraph(initialGraph: GraphData) {
  const [past, setPast] = useState<GraphSnapshot[]>([])
  const [present, setPresent] = useState<GraphSnapshot>(() => cloneGraph(initialGraph))
  const [future, setFuture] = useState<GraphSnapshot[]>([])

  const setGraph = useCallback((updater: (current: GraphData) => GraphData): void => {
    setPast((prevPast) => [...prevPast, cloneGraph(present)])
    setPresent((prevPresent) => cloneGraph(updater(prevPresent)))
    setFuture([])
  }, [present])

  const replaceGraph = useCallback((graph: GraphData): void => {
    setPast([])
    setPresent(cloneGraph(graph))
    setFuture([])
  }, [])

  const undo = useCallback((): void => {
    setPast((prevPast) => {
      if (prevPast.length === 0) {
        return prevPast
      }
      const previous = prevPast[prevPast.length - 1]
      setFuture((prevFuture) => [cloneGraph(present), ...prevFuture])
      setPresent(cloneGraph(previous))
      return prevPast.slice(0, -1)
    })
  }, [present])

  const redo = useCallback((): void => {
    setFuture((prevFuture) => {
      if (prevFuture.length === 0) {
        return prevFuture
      }
      const [next, ...rest] = prevFuture
      setPast((prevPast) => [...prevPast, cloneGraph(present)])
      setPresent(cloneGraph(next))
      return rest
    })
  }, [present])

  const controls = useMemo(
    () => ({
      canUndo: past.length > 0,
      canRedo: future.length > 0,
    }),
    [past.length, future.length],
  )

  return {
    graph: present as GraphData,
    setGraph,
    replaceGraph,
    undo,
    redo,
    ...controls,
  }
}
