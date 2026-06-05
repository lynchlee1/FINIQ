import type { GraphData, GraphNode, GraphEdge } from '../types/graph'
import corporateGraphData from '../examples/corporate-graph.json'

const API_BASE_URL = 'http://localhost:8000/api'

export class ApiClient {
  private isFallbackMode = true;

  constructor() {
    // Basic check if we can reach the backend
    this.checkHealth()
  }

  private async checkHealth() {
    try {
      const res = await fetch(`${API_BASE_URL}/graph`)
      if (res.ok) {
        this.isFallbackMode = false
      }
    } catch {
      this.isFallbackMode = true
    }
  }

  public getMode(): 'api' | 'fallback' {
    return this.isFallbackMode ? 'fallback' : 'api'
  }

  private getLocalGraph(): GraphData {
    const raw = localStorage.getItem('finiq_local_graph')
    if (raw) {
      try {
        return JSON.parse(raw)
      } catch (e) {
        // pass
      }
    }
    const defaultData = corporateGraphData as unknown as GraphData
    localStorage.setItem('finiq_local_graph', JSON.stringify(defaultData))
    return defaultData
  }

  private saveLocalGraph(graph: GraphData) {
    localStorage.setItem('finiq_local_graph', JSON.stringify(graph))
  }

  public async fetchGraph(): Promise<GraphData> {
    if (this.isFallbackMode) return this.getLocalGraph()
    const res = await fetch(`${API_BASE_URL}/graph`)
    if (!res.ok) throw new Error('Failed to fetch graph from API')
    return res.json()
  }

  public async addNode(node: Partial<GraphNode>): Promise<void> {
    if (this.isFallbackMode) {
      const graph = this.getLocalGraph()
      graph.nodes.push(node as GraphNode)
      this.saveLocalGraph(graph)
      return
    }
    const res = await fetch(`${API_BASE_URL}/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(node)
    })
    if (!res.ok) throw new Error('Failed to add node')
  }

  public async addEdge(edge: Partial<GraphEdge>): Promise<void> {
    if (this.isFallbackMode) {
      const graph = this.getLocalGraph()
      graph.edges.push(edge as GraphEdge)
      this.saveLocalGraph(graph)
      return
    }
    const res = await fetch(`${API_BASE_URL}/edges`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(edge)
    })
    if (!res.ok) throw new Error('Failed to add edge')
  }

  public async deleteNode(id: string): Promise<void> {
    if (this.isFallbackMode) {
      const graph = this.getLocalGraph()
      graph.nodes = graph.nodes.filter((n) => n.id !== id)
      graph.edges = graph.edges.filter(
        (e) =>
          (typeof e.source === 'string' ? e.source : e.source.id) !== id &&
          (typeof e.target === 'string' ? e.target : e.target.id) !== id
      )
      this.saveLocalGraph(graph)
      return
    }
    const res = await fetch(`${API_BASE_URL}/nodes/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete node')
  }

  public async deleteEdge(id: string): Promise<void> {
    if (this.isFallbackMode) {
      const graph = this.getLocalGraph()
      graph.edges = graph.edges.filter((e) => e.id !== id)
      this.saveLocalGraph(graph)
      return
    }
    const res = await fetch(`${API_BASE_URL}/edges/${id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error('Failed to delete edge')
  }

  public async runCustomCypher(query: string): Promise<GraphData> {
    if (this.isFallbackMode) {
      throw new Error('Custom Cypher execution is only available when connected to the backend API.')
    }
    const res = await fetch(`${API_BASE_URL}/cypher`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    })
    if (!res.ok) throw new Error('Failed to execute cypher query')
    return res.json()
  }

  public async seedDefaultData(): Promise<void> {
    if (this.isFallbackMode) {
      const defaultData = corporateGraphData as unknown as GraphData
      this.saveLocalGraph(defaultData)
      return
    }
    // Need a seed endpoint in the backend, or fallback to API batch insert
    const data = corporateGraphData as unknown as GraphData
    for (const node of data.nodes) await this.addNode(node)
    for (const edge of data.edges) await this.addEdge(edge)
  }
}

export const apiClient = new ApiClient()
