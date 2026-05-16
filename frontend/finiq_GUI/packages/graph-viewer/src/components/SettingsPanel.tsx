import { useState } from 'react'
import type { GraphStyleConfig, LayoutConfig, NodeShape, NodeTypeStyle } from '../types/graph'
import { 
  Button, 
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Label, 
  Tabs, TabsContent, TabsList, TabsTrigger,
  Card 
} from '@finiq/ui'
import { Settings2, Zap, Palette } from 'lucide-react'

interface SettingsPanelProps {
  style: GraphStyleConfig
  layout: LayoutConfig
  nodeTypes: string[]
  presetNames: string[]
  onStyleChange: (next: GraphStyleConfig) => void
  onLayoutChange: (next: LayoutConfig) => void
  onPresetChange: (presetName: string) => void
  onPresetSave: (presetName: string) => void
}

const NODE_SHAPES: NodeShape[] = ['circle', 'square', 'diamond', 'triangle']

export function SettingsPanel(props: SettingsPanelProps) {
  const {
    style,
    layout,
    nodeTypes,
    presetNames,
    onStyleChange,
    onLayoutChange,
    onPresetChange,
    onPresetSave,
  } = props
  const [draftLayout, setDraftLayout] = useState(layout)
  const [selectedNodeType, setSelectedNodeType] = useState<string>('')
  const effectiveNodeType = nodeTypes.includes(selectedNodeType) ? selectedNodeType : (nodeTypes[0] ?? '')
  const effectiveNodeTypeStyle = effectiveNodeType
    ? (style.nodeTypeStyles?.[effectiveNodeType] || {
        color: style.nodeColor,
        size: style.nodeSize,
        shape: 'circle',
        borderColor: style.nodeBorderColor,
        borderWidth: style.nodeBorderWidth,
      })
    : {
        color: style.nodeColor,
        size: style.nodeSize,
        shape: 'circle',
        borderColor: style.nodeBorderColor,
        borderWidth: style.nodeBorderWidth,
      }

  const hasDraftLayoutChanges =
    draftLayout.linkDistance !== layout.linkDistance ||
    draftLayout.chargeStrength !== layout.chargeStrength ||
    draftLayout.collisionRadius !== layout.collisionRadius ||
    draftLayout.alphaDecay !== layout.alphaDecay

  const applyDraftLayout = (): void => {
    onLayoutChange({
      ...layout,
      linkDistance: draftLayout.linkDistance,
      chargeStrength: draftLayout.chargeStrength,
      collisionRadius: draftLayout.collisionRadius,
      alphaDecay: draftLayout.alphaDecay,
    })
  }

  const updateNodeTypeStyle = (patch: Partial<NodeTypeStyle>): void => {
    if (!effectiveNodeType) {
      return
    }
    onStyleChange({
      ...style,
      nodeTypeStyles: {
        ...(style.nodeTypeStyles ?? {}),
        [effectiveNodeType]: {
          ...effectiveNodeTypeStyle as NodeTypeStyle,
          ...patch,
        },
      },
    })
  }

  return (
    <Card className="border-t-0 rounded-t-none">
      <Tabs defaultValue="board" className="w-full">
        <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/20">
          <TabsList className="h-8 bg-transparent gap-4">
            <TabsTrigger value="board" className="data-[state=active]:bg-background data-[state=active]:shadow-sm px-3 text-xs gap-1.5">
              <Palette className="w-3.5 h-3.5" /> Board
            </TabsTrigger>
            <TabsTrigger value="node" className="data-[state=active]:bg-background data-[state=active]:shadow-sm px-3 text-xs gap-1.5">
              <Zap className="w-3.5 h-3.5" /> Node Style
            </TabsTrigger>
            <TabsTrigger value="physics" className="data-[state=active]:bg-background data-[state=active]:shadow-sm px-3 text-xs gap-1.5">
              <Settings2 className="w-3.5 h-3.5" /> Physics
            </TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            <Label className="text-[10px] uppercase font-bold text-muted-foreground">Preset</Label>
            <Select value={style.presetName} onValueChange={onPresetChange}>
              <SelectTrigger className="h-7 w-[120px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {presetNames.map((name) => (
                  <SelectItem key={name} value={name}>{name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <TabsContent value="board" className="p-4 m-0 grid grid-cols-4 gap-6">
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Background</Label>
              <div className="flex gap-2 items-center">
                <input
                  type="color"
                  value={style.backgroundColor}
                  onChange={(event) => onStyleChange({ ...style, backgroundColor: event.target.value })}
                  className="w-8 h-8 rounded border p-0.5 cursor-pointer"
                />
                <span className="text-[11px] font-mono uppercase">{style.backgroundColor}</span>
              </div>
            </div>
          </div>
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Default Node</Label>
              <input
                type="color"
                value={style.nodeColor}
                onChange={(event) => onStyleChange({ ...style, nodeColor: event.target.value })}
                className="w-full h-8 rounded border p-0.5 cursor-pointer"
              />
            </div>
          </div>
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Default Edge</Label>
              <input
                type="color"
                value={style.edgeColor}
                onChange={(event) => onStyleChange({ ...style, edgeColor: event.target.value })}
                className="w-full h-8 rounded border p-0.5 cursor-pointer"
              />
            </div>
          </div>
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Node Size ({style.nodeSize})</Label>
              <input
                type="range"
                min={2}
                max={20}
                value={style.nodeSize}
                onChange={(event) => onStyleChange({ ...style, nodeSize: Number(event.target.value) })}
                className="w-full h-4 accent-primary"
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="node" className="p-4 m-0 grid grid-cols-4 gap-6">
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Target Type</Label>
              <Select value={effectiveNodeType} onValueChange={setSelectedNodeType}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {nodeTypes.map((type) => (
                    <SelectItem key={type} value={type}>{type}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Shape</Label>
              <Select
                value={effectiveNodeTypeStyle.shape}
                onValueChange={(value) => updateNodeTypeStyle({ shape: value as NodeShape })}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {NODE_SHAPES.map((shape) => (
                    <SelectItem key={shape} value={shape}>{shape}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-3">
            <div className="grid gap-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Color</Label>
              <input
                type="color"
                value={effectiveNodeTypeStyle.color}
                onChange={(event) => updateNodeTypeStyle({ color: event.target.value })}
                className="w-full h-8 rounded border p-0.5 cursor-pointer"
              />
            </div>
          </div>
          <div className="space-y-3 flex items-end">
            <Button variant="outline" size="sm" className="w-full text-xs" onClick={() => onPresetSave(style.presetName)}>
              Apply Globally
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="physics" className="p-4 m-0 flex items-center justify-between">
          <div className="flex gap-8 flex-1">
            <div className="space-y-1.5 flex-1 max-w-[200px]">
              <Label className="text-[10px] uppercase text-muted-foreground tracking-tight">Distance ({draftLayout.linkDistance})</Label>
              <input
                type="range"
                min={20}
                max={320}
                value={draftLayout.linkDistance}
                onChange={(event) => setDraftLayout({ ...draftLayout, linkDistance: Number(event.target.value) })}
                className="w-full h-4 accent-primary"
              />
            </div>
            <div className="space-y-1.5 flex-1 max-w-[200px]">
              <Label className="text-[10px] uppercase text-muted-foreground tracking-tight">Repulsion ({draftLayout.chargeStrength})</Label>
              <input
                type="range"
                min={-700}
                max={-10}
                value={draftLayout.chargeStrength}
                onChange={(event) => setDraftLayout({ ...draftLayout, chargeStrength: Number(event.target.value) })}
                className="w-full h-4 accent-primary"
              />
            </div>
            <div className="space-y-1.5 flex-1 max-w-[200px]">
              <Label className="text-[10px] uppercase text-muted-foreground tracking-tight">Collision ({draftLayout.collisionRadius})</Label>
              <input
                type="range"
                min={1}
                max={40}
                value={draftLayout.collisionRadius}
                onChange={(event) => setDraftLayout({ ...draftLayout, collisionRadius: Number(event.target.value) })}
                className="w-full h-4 accent-primary"
              />
            </div>
          </div>
          
          <div className="flex gap-2">
            <Button 
              size="sm" 
              className="h-8 text-xs font-bold" 
              disabled={!hasDraftLayoutChanges}
              onClick={applyDraftLayout}
            >
              Reheat Simulation
            </Button>
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs" 
              disabled={!hasDraftLayoutChanges}
              onClick={() => setDraftLayout(layout)}
            >
              Reset
            </Button>
          </div>
        </TabsContent>
      </Tabs>
    </Card>
  )
}
