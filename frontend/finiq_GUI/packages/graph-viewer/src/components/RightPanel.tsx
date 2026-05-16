import type { GraphData, GraphEdge, GraphNode } from '../types/graph'
import { 
  Button, 
  Input, 
  Label, 
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Card, CardContent, CardHeader, CardTitle,
  Tabs, TabsContent, TabsList, TabsTrigger 
} from '@finiq/ui'
import { Info, Link as LinkIcon, History, MapPin, Trash2, Pin, PinOff, Move, Layers } from 'lucide-react'

interface RightPanelProps {
  graph: GraphData
  selectedNode: GraphNode | undefined
  selectedEdge: GraphEdge | undefined
  selectedNodeIds: Set<string>
  selectedEdgeIds: Set<string>
  visitHistory: string[]
  shortestPath: string[]
  onNodePatch: (nodeId: string, patch: Partial<GraphNode>) => void
  onEdgePatch: (edgeId: string, patch: Partial<GraphEdge>) => void
  onDeleteNode: (nodeId: string) => void
  onDeleteEdge: (edgeId: string) => void
  onPinNode: (nodeId: string, pinned: boolean) => void
  onHideSelected: () => void
  onShowHidden: () => void
  onApplyNeighborhood: () => void
  onJumpSelected: () => void
}

export function RightPanel(props: RightPanelProps) {
  const {
    selectedNode,
    selectedEdge,
    selectedNodeIds,
    selectedEdgeIds,
    visitHistory,
    shortestPath,
    onNodePatch,
    onEdgePatch,
    onDeleteNode,
    onDeleteEdge,
    onPinNode,
    onHideSelected,
    onShowHidden,
    onApplyNeighborhood,
    onJumpSelected,
  } = props

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pl-1">
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-xs flex items-center justify-between uppercase tracking-wider">
            <span className="flex items-center gap-2">
              <Layers className="w-4 h-4" />
              Selection
            </span>
            <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">
              {selectedNodeIds.size}N / {selectedEdgeIds.size}E
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-2 grid grid-cols-2 gap-2">
          <Button variant="outline" size="xs" className="text-[11px]" onClick={onJumpSelected}>
            <Move className="w-3 h-3 mr-1" /> Jump
          </Button>
          <Button variant="outline" size="xs" className="text-[11px]" onClick={onApplyNeighborhood}>
            N-Hop
          </Button>
          <Button variant="outline" size="xs" className="text-[11px]" onClick={onHideSelected}>
            Hide
          </Button>
          <Button variant="outline" size="xs" className="text-[11px]" onClick={onShowHidden}>
            Show All
          </Button>
        </CardContent>
      </Card>

      <Tabs defaultValue="details" className="flex-1 flex flex-col min-height-0">
        <TabsList className="grid grid-cols-2 h-9">
          <TabsTrigger value="details" className="text-xs">Details</TabsTrigger>
          <TabsTrigger value="analysis" className="text-xs">Insights</TabsTrigger>
        </TabsList>

        <TabsContent value="details" className="flex-1 mt-2 space-y-4">
          <Card>
            <CardHeader className="p-3 pb-1">
              <CardTitle className="text-[11px] flex items-center gap-1.5 uppercase tracking-tighter text-muted-foreground">
                <Info className="w-3.5 h-3.5" />
                Node Details
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-2">
              {!selectedNode ? (
                <p className="text-xs text-muted-foreground italic">Select a node to inspect.</p>
              ) : (
                <div className="space-y-3">
                  <div className="grid gap-1.5">
                    <Label className="text-[10px] uppercase text-muted-foreground">ID</Label>
                    <Input value={selectedNode.id} disabled className="h-7 text-xs bg-muted/30" />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-[10px] uppercase text-muted-foreground">Label</Label>
                    <Input
                      value={selectedNode.label}
                      onChange={(event) => onNodePatch(selectedNode.id, { label: event.target.value })}
                      className="h-7 text-xs"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1.5">
                      <Label className="text-[10px] uppercase text-muted-foreground">Risk Level</Label>
                      <Select
                        value={selectedNode.riskLevel ?? 'low'}
                        onValueChange={(value) => onNodePatch(selectedNode.id, { riskLevel: value as any })}
                      >
                        <SelectTrigger className="h-7 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Low</SelectItem>
                          <SelectItem value="medium">Medium</SelectItem>
                          <SelectItem value="high">High</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-end gap-1">
                      <Button 
                        variant="outline" 
                        size="icon-sm" 
                        className="w-full h-7"
                        onClick={() => onPinNode(selectedNode.id, !selectedNode.pinned)}
                      >
                        {selectedNode.pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                      </Button>
                      <Button 
                        variant="destructive" 
                        size="icon-sm" 
                        className="w-full h-7"
                        onClick={() => onDeleteNode(selectedNode.id)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-3 pb-1">
              <CardTitle className="text-[11px] flex items-center gap-1.5 uppercase tracking-tighter text-muted-foreground">
                <LinkIcon className="w-3.5 h-3.5" />
                Edge Details
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-2">
              {!selectedEdge ? (
                <p className="text-xs text-muted-foreground italic">Select an edge to inspect.</p>
              ) : (
                <div className="space-y-3">
                  <div className="grid gap-1.5">
                    <Label className="text-[10px] uppercase text-muted-foreground">Relation</Label>
                    <Input
                      value={selectedEdge.relation}
                      onChange={(event) => onEdgePatch(selectedEdge.id, { relation: event.target.value })}
                      className="h-7 text-xs"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1.5">
                      <Label className="text-[10px] uppercase text-muted-foreground">Category</Label>
                      <Select
                        value={selectedEdge.category}
                        onValueChange={(value) => onEdgePatch(selectedEdge.id, { category: value as any })}
                      >
                        <SelectTrigger className="h-7 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="equity">Equity</SelectItem>
                          <SelectItem value="personnel">Personnel</SelectItem>
                          <SelectItem value="address">Address</SelectItem>
                          <SelectItem value="transaction">Transaction</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-end">
                      <Button 
                        variant="destructive" 
                        size="xs" 
                        className="w-full h-7 text-[10px]"
                        onClick={() => onDeleteEdge(selectedEdge.id)}
                      >
                        Delete Edge
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analysis" className="flex-1 mt-2 space-y-4">
          <Card>
            <CardHeader className="p-3 pb-1">
              <CardTitle className="text-[11px] flex items-center gap-1.5 uppercase tracking-tighter text-muted-foreground">
                <History className="w-3.5 h-3.5" />
                History
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-2">
              {visitHistory.length === 0 ? (
                <p className="text-[10px] text-muted-foreground italic">No visits yet.</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {visitHistory.slice(-10).map((id, idx) => (
                    <span key={`${id}-${idx}`} className="text-[10px] bg-muted px-1.5 py-0.5 rounded-sm border truncate max-w-[80px]">
                      {id}
                    </span>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-3 pb-1">
              <CardTitle className="text-[11px] flex items-center gap-1.5 uppercase tracking-tighter text-muted-foreground">
                <MapPin className="w-3.5 h-3.5" />
                Path Finder
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-2">
              {shortestPath.length <= 1 ? (
                <p className="text-[10px] text-muted-foreground italic">Select two nodes for path.</p>
              ) : (
                <div className="space-y-1">
                  {shortestPath.map((id, idx) => (
                    <div key={id} className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-primary" />
                      <span className="text-[11px] font-medium truncate">{id}</span>
                      {idx < shortestPath.length - 1 && <div className="w-px h-2 bg-muted mx-1" />}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
