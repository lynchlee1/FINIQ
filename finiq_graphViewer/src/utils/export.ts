import type { GraphData, GraphStyleConfig } from '../types/graph'

function toNodeId(value: { id: string } | string): string {
  return typeof value === 'string' ? value : value.id
}

function downloadBlob(content: BlobPart, filename: string, type: string): void {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export function exportGraphJson(graph: GraphData, filename = 'graph.json'): void {
  const plain = {
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      type: node.type,
      group: node.group,
      tags: node.tags,
      properties: node.properties,
      pinned: node.pinned ?? false,
      x: node.x,
      y: node.y,
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: toNodeId(edge.source as { id: string } | string),
      target: toNodeId(edge.target as { id: string } | string),
      relation: edge.relation,
      weight: edge.weight,
      directed: edge.directed,
      properties: edge.properties,
    })),
  }
  downloadBlob(JSON.stringify(plain, null, 2), filename, 'application/json')
}

export function exportStyleJson(style: GraphStyleConfig, filename = 'graph-style.json'): void {
  downloadBlob(JSON.stringify(style, null, 2), filename, 'application/json')
}

export function exportLayoutJson(graph: GraphData, filename = 'graph-layout.json'): void {
  const layout = {
    positions: graph.nodes.map((node) => ({
      id: node.id,
      x: node.x,
      y: node.y,
      fx: node.fx,
      fy: node.fy,
      pinned: Boolean(node.pinned),
    })),
  }
  downloadBlob(JSON.stringify(layout, null, 2), filename, 'application/json')
}

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;')
}

export function exportVisibleSvg(
  graph: GraphData,
  width: number,
  height: number,
  backgroundColor: string,
  filename = 'graph.svg',
): void {
  if (graph.nodes.length === 0) {
    return
  }

  const validNodes = graph.nodes.filter(
    (node) => typeof node.x === 'number' && typeof node.y === 'number',
  )
  if (validNodes.length === 0) {
    return
  }

  const xs = validNodes.map((node) => node.x as number)
  const ys = validNodes.map((node) => node.y as number)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = Math.max(1, maxX - minX)
  const spanY = Math.max(1, maxY - minY)
  const pad = 32

  const sx = (width - pad * 2) / spanX
  const sy = (height - pad * 2) / spanY
  const scale = Math.min(sx, sy)

  const tx = (x: number) => (x - minX) * scale + pad
  const ty = (y: number) => (y - minY) * scale + pad

  const nodeById = new Map<string, (typeof graph.nodes)[number]>()
  graph.nodes.forEach((node) => nodeById.set(node.id, node))

  const edgeLines = graph.edges
    .map((edge) => {
      const sourceId = toNodeId(edge.source as { id: string } | string)
      const targetId = toNodeId(edge.target as { id: string } | string)
      const source = nodeById.get(sourceId)
      const target = nodeById.get(targetId)
      if (!source || !target || typeof source.x !== 'number' || typeof target.x !== 'number' || typeof source.y !== 'number' || typeof target.y !== 'number') {
        return ''
      }
      return `<line x1="${tx(source.x)}" y1="${ty(source.y)}" x2="${tx(target.x)}" y2="${ty(target.y)}" stroke="#8792a2" stroke-width="${Math.max(1, edge.weight * 0.5)}" opacity="0.8" />`
    })
    .join('')

  const nodeCircles = validNodes
    .map((node) => {
      const x = tx(node.x as number)
      const y = ty(node.y as number)
      return `<g><circle cx="${x}" cy="${y}" r="5" fill="#6366f1" stroke="#111827" stroke-width="1"/><text x="${x + 8}" y="${y - 8}" font-size="10" fill="#e5e7eb">${escapeXml(node.label)}</text></g>`
    })
    .join('')

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="${backgroundColor}" />${edgeLines}${nodeCircles}</svg>`
  downloadBlob(svg, filename, 'image/svg+xml')
}

export function exportCanvasPng(canvas: HTMLCanvasElement, filename = 'graph.png'): void {
  canvas.toBlob((blob) => {
    if (!blob) {
      return
    }
    downloadBlob(blob, filename, 'image/png')
  })
}
