import { useState, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle, Button, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@finiq/ui'
import { PlusCircle } from 'lucide-react'
import { apiClient } from '../utils/apiClient'
import type { GraphData, GraphNode } from '../types/graph'

interface RelationshipEdgeFormProps {
  graph: GraphData
  onRefreshGraph: () => void
}

export function RelationshipEdgeForm({ graph, onRefreshGraph }: RelationshipEdgeFormProps) {
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [relationName, setRelationName] = useState('')
  const [category, setCategory] = useState<'equity' | 'personnel' | 'address' | 'transaction' | 'other'>('transaction')
  const [weight, setWeight] = useState('0')
  const [directed, setDirected] = useState(true)
  const [edgeSuccessMsg, setEdgeSuccessMsg] = useState('')

  const nodeOptions = useMemo(() => graph.nodes.map((n: GraphNode) => ({ id: n.id, label: n.label })), [graph.nodes])

  const handleAddEdge = async () => {
    setEdgeSuccessMsg('')
    if (!sourceId || !targetId || !relationName) {
      alert('Source Node ID, Target Node ID, and Relationship label are required.')
      return
    }

    try {
      const edgeData = {
        id: `e-${sourceId}-${targetId}-${Date.now()}`,
        source: sourceId,
        target: targetId,
        relation: relationName.trim(),
        category,
        weight: Number(weight) || 0,
        directed,
        properties: {},
      }

      await apiClient.addEdge(edgeData)
      setEdgeSuccessMsg(`Successfully created relationship: ${sourceId} ➔ ${targetId}`)
      onRefreshGraph()

      setRelationName('')
      setWeight('0')
    } catch (e: any) {
      alert(`Failed to create relationship: ${e.message}`)
    }
  }

  return (
    <Card className="bg-card/40">
      <CardHeader className="p-4 border-b">
        <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <PlusCircle className="w-4 h-4 text-green-400" /> Create Corporate Relationship Link
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Source Node (e.g. Origin)</Label>
            <Select value={sourceId} onValueChange={setSourceId}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select Source Entity" />
              </SelectTrigger>
              <SelectContent>
                {nodeOptions.map((opt: { id: string, label: string }) => (
                  <SelectItem key={opt.id} value={opt.id}>
                    {opt.label} ({opt.id})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Target Node (e.g. Recipient)</Label>
            <Select value={targetId} onValueChange={setTargetId}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select Target Entity" />
              </SelectTrigger>
              <SelectContent>
                {nodeOptions.map((opt: { id: string, label: string }) => (
                  <SelectItem key={opt.id} value={opt.id}>
                    {opt.label} ({opt.id})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Relationship Name Label</Label>
            <Input value={relationName} onChange={(e) => setRelationName(e.target.value)} placeholder="e.g. Supplies Chipsets, Largest Shareholder" className="h-8 text-xs" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Relationship Category</Label>
            <Select value={category} onValueChange={(val) => setCategory(val as any)}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="transaction">Transaction (Supply Chain)</SelectItem>
                <SelectItem value="equity">Equity (Shares/Ownership)</SelectItem>
                <SelectItem value="personnel">Personnel (Executive/Director)</SelectItem>
                <SelectItem value="address">Address (Geographics)</SelectItem>
                <SelectItem value="other">Other / Competitors</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 items-end">
          <div className="grid gap-1.5">
            <Label className="text-xs">Transaction Stake / Cost weight (%)</Label>
            <Input type="number" min="0" max="100" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="e.g. 15" className="h-8 text-xs font-mono" />
          </div>
          <div className="flex items-center gap-2 py-2 select-none">
            <input
              type="checkbox"
              id="directed-check"
              checked={directed}
              onChange={(e) => setDirected(e.target.checked)}
              className="rounded border-muted text-primary focus:ring-primary w-4 h-4"
            />
            <Label htmlFor="directed-check" className="text-xs cursor-pointer">Directed Connection (A ➔ B)</Label>
          </div>
        </div>

        {edgeSuccessMsg && (
          <div className="p-2 bg-green-500/10 border border-green-500/30 text-green-500 text-xs rounded font-medium">
            {edgeSuccessMsg}
          </div>
        )}

        <div className="flex justify-end pt-4">
          <Button size="sm" onClick={handleAddEdge} className="text-xs font-bold flex items-center gap-1">
            <PlusCircle className="w-3.5 h-3.5" /> Create Link
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
