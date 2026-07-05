import type { GraphData, GraphNode, GraphEdge } from '../types/graph'
import corporateGraphData from '../examples/corporate-graph.json'

const API_BASE_URL = 'http://localhost:8000/api'

export class ApiClient {
  private async request(path: string, init?: RequestInit): Promise<Response> {
    const res = await fetch(`${API_BASE_URL}${path}`, init)
    if (!res.ok) {
      throw new Error(`API request failed: ${res.status} ${res.statusText}`)
    }
    return res
  }

  public async fetchGraph(): Promise<GraphData> {
    const res = await this.request('/graph')
    return res.json()
  }

  public async addNode(node: Partial<GraphNode>): Promise<void> {
    await this.request('/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(node)
    })
  }

  public async addEdge(edge: Partial<GraphEdge>): Promise<void> {
    await this.request('/edges', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(edge)
    })
  }

  public async deleteNode(id: string): Promise<void> {
    await this.request(`/nodes/${id}`, {
      method: 'DELETE',
    })
  }

  public async deleteEdge(id: string): Promise<void> {
    await this.request(`/edges/${id}`, {
      method: 'DELETE',
    })
  }

  public async runCustomCypher(query: string): Promise<GraphData> {
    const res = await this.request('/cypher', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    })
    return res.json()
  }

  public async seedDefaultData(): Promise<void> {
    const data = corporateGraphData as unknown as GraphData
    for (const node of data.nodes) await this.addNode(node)
    for (const edge of data.edges) await this.addEdge(edge)
  }
}

export const apiClient = new ApiClient()
