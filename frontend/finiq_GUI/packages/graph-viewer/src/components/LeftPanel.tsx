import { useMemo } from 'react'
import type { FilterState, GraphData } from '../types/graph'
import { 
  Button, 
  Input, 
  Label, 
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Card, CardContent, CardHeader, CardTitle 
} from '@finiq/ui'
import { ShieldCheck, Search, Filter } from 'lucide-react'

interface LeftPanelProps {
  searchText: string
  onSearchTextChange: (value: string) => void
  filters: FilterState
  onFiltersChange: (next: FilterState) => void
  graph: GraphData
  runCorporateAnalysis?: () => void
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values))
}

export function LeftPanel(props: LeftPanelProps) {
  const {
    searchText,
    onSearchTextChange,
    filters,
    onFiltersChange,
    graph,
    runCorporateAnalysis,
  } = props

  const options = useMemo(
    () => ({
      nodeTypes: unique(graph.nodes.map((n) => n.type)).sort(),
      groups: unique(graph.nodes.map((n) => n.group ?? '')).filter(Boolean).sort(),
      tags: unique(graph.nodes.flatMap((n) => n.tags)).sort(),
      relations: unique(graph.edges.map((e) => e.relation)).sort(),
      categories: unique(graph.edges.map((e) => e.category)).sort(),
    }),
    [graph],
  )

  const toggle = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value]

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pr-1">
      {runCorporateAnalysis && (
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-xs flex items-center gap-2 uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4 text-primary" />
              Corporate Analysis
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <Button 
              onClick={runCorporateAnalysis} 
              className="w-full font-bold"
              variant="default"
            >
              Run Analysis Engine
            </Button>
            <p className="text-[10px] text-muted-foreground mt-2">
              Detects hidden links and analyzes governance risks.
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-xs flex items-center gap-2 uppercase tracking-wider">
            <Search className="w-4 h-4" />
            Search
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <Input
            value={searchText}
            onChange={(event) => onSearchTextChange(event.target.value)}
            placeholder="Search entities, relations..."
            className="h-8 text-sm"
          />
        </CardContent>
      </Card>

      <Card className="flex-1">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-xs flex items-center gap-2 uppercase tracking-wider">
            <Filter className="w-4 h-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0 space-y-4">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Logic</Label>
              <Select
                value={filters.logic}
                onValueChange={(value) => onFiltersChange({ ...filters, logic: value as any })}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="AND">AND</SelectItem>
                  <SelectItem value="OR">OR</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Direction</Label>
              <Select
                value={filters.direction}
                onValueChange={(value) => onFiltersChange({ ...filters, direction: value as any })}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="directed">Directed</SelectItem>
                  <SelectItem value="undirected">Undirected</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Relation Category</Label>
              <div className="flex flex-wrap gap-1.5">
                {options.categories.map((category) => (
                  <Button
                    key={category}
                    variant={filters.edgeCategories.includes(category as any) ? "default" : "outline"}
                    size="xs"
                    className="h-6 text-[11px] px-2 capitalize"
                    onClick={() => onFiltersChange({ ...filters, edgeCategories: toggle(filters.edgeCategories as string[], category) as any })}
                  >
                    {category}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase text-muted-foreground">Node Types</Label>
              <div className="flex flex-wrap gap-1.5">
                {options.nodeTypes.map((type) => (
                  <Button
                    key={type}
                    variant={filters.nodeTypes.includes(type) ? "default" : "outline"}
                    size="xs"
                    className="h-6 text-[11px] px-2"
                    onClick={() => onFiltersChange({ ...filters, nodeTypes: toggle(filters.nodeTypes, type) })}
                  >
                    {type}
                  </Button>
                ))}
              </div>
            </div>
          </div>

          <div className="pt-2 border-t flex items-center gap-2">
            <input
              type="checkbox"
              id="hide-isolated"
              checked={filters.hideIsolated}
              onChange={(event) => onFiltersChange({ ...filters, hideIsolated: event.target.checked })}
              className="w-3.5 h-3.5"
            />
            <Label htmlFor="hide-isolated" className="text-xs font-normal cursor-pointer">
              Hide isolated nodes
            </Label>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
