import { useMemo } from 'react'
import type { FilterState, GraphData } from '../types/graph'

interface LeftPanelProps {
  searchText: string
  onSearchTextChange: (value: string) => void
  filters: FilterState
  onFiltersChange: (next: FilterState) => void
  graph: GraphData
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
  } = props

  const options = useMemo(
    () => ({
      nodeTypes: unique(graph.nodes.map((n) => n.type)).sort(),
      groups: unique(graph.nodes.map((n) => n.group ?? '')).filter(Boolean).sort(),
      tags: unique(graph.nodes.flatMap((n) => n.tags)).sort(),
      relations: unique(graph.edges.map((e) => e.relation)).sort(),
    }),
    [graph],
  )

  const toggle = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value]

  return (
    <div className="side-panel left-panel">
      <section>
        <h2>Search</h2>
        <div className="feature-row">
          <input
            value={searchText}
            onChange={(event) => onSearchTextChange(event.target.value)}
            placeholder="id, label, type, tag, relation, properties..."
          />
        </div>
      </section>

      <section>
        <h2>Filters</h2>
        <div className="feature-row">
          <label>
            Logic
            <select
              value={filters.logic}
              onChange={(event) => onFiltersChange({ ...filters, logic: event.target.value as FilterState['logic'] })}
            >
              <option value="AND">AND</option>
              <option value="OR">OR</option>
            </select>
          </label>
        </div>
        <div className="feature-row">
          <label>
            Direction
            <select
              value={filters.direction}
              onChange={(event) =>
                onFiltersChange({ ...filters, direction: event.target.value as FilterState['direction'] })
              }
            >
              <option value="all">All</option>
              <option value="directed">Directed only</option>
              <option value="undirected">Undirected only</option>
            </select>
          </label>
        </div>
        <div className="feature-row">
          <label>
            Min weight
            <input
              type="number"
              step={0.1}
              value={filters.minWeight}
              onChange={(event) => onFiltersChange({ ...filters, minWeight: Number(event.target.value) || 0 })}
            />
          </label>
        </div>
        <div className="feature-row">
          <label>
            Min degree
            <input
              type="number"
              value={filters.minDegree}
              onChange={(event) => onFiltersChange({ ...filters, minDegree: Number(event.target.value) || 0 })}
            />
          </label>
        </div>

        <details>
          <summary>Node type</summary>
          <div className="pill-wrap">
            {options.nodeTypes.map((type) => (
              <button
                key={type}
                type="button"
                className={filters.nodeTypes.includes(type) ? 'pill active' : 'pill'}
                onClick={() => onFiltersChange({ ...filters, nodeTypes: toggle(filters.nodeTypes, type) })}
              >
                {type}
              </button>
            ))}
          </div>
        </details>

        <details>
          <summary>Group</summary>
          <div className="pill-wrap">
            {options.groups.map((group) => (
              <button
                key={group}
                type="button"
                className={filters.groups.includes(group) ? 'pill active' : 'pill'}
                onClick={() => onFiltersChange({ ...filters, groups: toggle(filters.groups, group) })}
              >
                {group}
              </button>
            ))}
          </div>
        </details>

        <details>
          <summary>Tag</summary>
          <div className="pill-wrap">
            {options.tags.map((tag) => (
              <button
                key={tag}
                type="button"
                className={filters.tags.includes(tag) ? 'pill active' : 'pill'}
                onClick={() => onFiltersChange({ ...filters, tags: toggle(filters.tags, tag) })}
              >
                {tag}
              </button>
            ))}
          </div>
        </details>

        <details>
          <summary>Edge relation</summary>
          <div className="pill-wrap">
            {options.relations.map((relation) => (
              <button
                key={relation}
                type="button"
                className={filters.edgeRelations.includes(relation) ? 'pill active' : 'pill'}
                onClick={() => onFiltersChange({ ...filters, edgeRelations: toggle(filters.edgeRelations, relation) })}
              >
                {relation}
              </button>
            ))}
          </div>
        </details>
        <label className="check-row">
          <input
            type="checkbox"
            checked={filters.hideIsolated}
            onChange={(event) => onFiltersChange({ ...filters, hideIsolated: event.target.checked })}
          />
          Hide isolated nodes
        </label>
      </section>
    </div>
  )
}
