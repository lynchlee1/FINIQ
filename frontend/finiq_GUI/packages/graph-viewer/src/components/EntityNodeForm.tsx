import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, Button, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@finiq/ui'
import { PlusCircle } from 'lucide-react'
import { apiClient } from '../utils/apiClient'

interface EntityNodeFormProps {
  onRefreshGraph: () => void
}

export function EntityNodeForm({ onRefreshGraph }: EntityNodeFormProps) {
  const [nodeId, setNodeId] = useState('')
  const [nodeLabel, setNodeLabel] = useState('')
  const [nodeType, setNodeType] = useState('Company')
  const [nodeGroup, setNodeGroup] = useState('')
  const [nodeTags, setNodeTags] = useState('')
  const [creditRating, setCreditRating] = useState('AAA')
  const [riskLevel, setRiskLevel] = useState<'low' | 'medium' | 'high'>('low')
  const [hq, setHq] = useState('')
  const [country, setCountry] = useState('')
  const [propertiesJson, setPropertiesJson] = useState('{}')
  const [nodeSuccessMsg, setNodeSuccessMsg] = useState('')

  const handleAddNode = async () => {
    setNodeSuccessMsg('')
    if (!nodeId || !nodeLabel) {
      alert('Node ID and Label are required.')
      return
    }

    try {
      let customProps = {}
      try {
        customProps = JSON.parse(propertiesJson || '{}')
      } catch (err) {
        alert('Invalid Custom Properties JSON format.')
        return
      }

      const nodeData = {
        id: nodeId.trim().toLowerCase().replace(/\s+/g, '-'),
        label: nodeLabel.trim(),
        type: nodeType,
        group: nodeGroup.trim() || undefined,
        tags: nodeTags.split(',').map((t) => t.trim()).filter(Boolean),
        riskLevel,
        properties: {
          ...customProps,
          creditRating,
          hq: hq.trim() || undefined,
          country: country.trim() || undefined,
        },
      }

      await apiClient.addNode(nodeData as any)
      setNodeSuccessMsg(`Successfully added entity node: ${nodeLabel}`)
      onRefreshGraph()

      setNodeId('')
      setNodeLabel('')
      setNodeGroup('')
      setNodeTags('')
      setHq('')
      setCountry('')
      setPropertiesJson('{}')
    } catch (e: any) {
      alert(`Failed to add entity: ${e.message}`)
    }
  }

  return (
    <Card className="bg-card/40">
      <CardHeader className="p-4 border-b">
        <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <PlusCircle className="w-4 h-4 text-green-400" /> Add Corporate / Person Entity
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Entity ID (Slug Key)</Label>
            <Input value={nodeId} onChange={(e) => setNodeId(e.target.value)} placeholder="e.g. sk-telecom" className="h-8 text-xs font-mono" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Display Label Name</Label>
            <Input value={nodeLabel} onChange={(e) => setNodeLabel(e.target.value)} placeholder="e.g. SK Telecom" className="h-8 text-xs" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Entity Classification</Label>
            <Select value={nodeType} onValueChange={setNodeType}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Company">Company</SelectItem>
                <SelectItem value="Person">Person</SelectItem>
                <SelectItem value="Group">Group / Conglomerate</SelectItem>
                <SelectItem value="Address">Geographic Address</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Corporate Group (Alliance)</Label>
            <Input value={nodeGroup} onChange={(e) => setNodeGroup(e.target.value)} placeholder="e.g. SK Group" className="h-8 text-xs" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Industry Tags (Comma Separated)</Label>
            <Input value={nodeTags} onChange={(e) => setNodeTags(e.target.value)} placeholder="Telecom, Tech" className="h-8 text-xs" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Credit Rating</Label>
            <Input value={creditRating} onChange={(e) => setCreditRating(e.target.value)} placeholder="e.g. AAA or A+" className="h-8 text-xs font-mono" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Headquarters Address</Label>
            <Input value={hq} onChange={(e) => setHq(e.target.value)} placeholder="Seoul, Korea" className="h-8 text-xs" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Country</Label>
            <Input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="South Korea" className="h-8 text-xs" />
          </div>
        </div>

        <div className="grid gap-1.5">
          <Label className="text-xs">Base Credit Risk Level</Label>
          <Select value={riskLevel} onValueChange={(val) => setRiskLevel(val as any)}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="low">Low Risk</SelectItem>
              <SelectItem value="medium">Medium Risk</SelectItem>
              <SelectItem value="high">High / Default Risk</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label className="text-xs">Custom Properties (JSON format)</Label>
          <textarea
            value={propertiesJson}
            onChange={(e) => setPropertiesJson(e.target.value)}
            rows={3}
            className="w-full text-xs font-mono p-2 border rounded bg-background/50 focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        {nodeSuccessMsg && (
          <div className="p-2 bg-green-500/10 border border-green-500/30 text-green-500 text-xs rounded font-medium">
            {nodeSuccessMsg}
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" onClick={handleAddNode} className="text-xs font-bold flex items-center gap-1">
            <PlusCircle className="w-3.5 h-3.5" /> Save Entity
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
