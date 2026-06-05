import { useState } from 'react'
import type { GraphStyleConfig, LayoutConfig, NodeShape, NodeTypeStyle } from '../types/graph'

type ControlSection = 'board' | 'node' | 'focus' | 'physics'

interface SettingsPanelProps {
  style: GraphStyleConfig
  layout: LayoutConfig
  nodeTypes: string[]
  presetNames: string[]
  onStyleChange: (next: GraphStyleConfig) => void
  onLayoutChange: (next: LayoutConfig) => void
  onPresetChange: (presetName: string) => void
  onPresetAdd: (presetName: string) => void
  onPresetRemove: (presetName: string) => void
  onPresetSave: (presetName: string) => void
}

const NODE_SHAPES: NodeShape[] = ['circle', 'square', 'diamond', 'triangle']
const CONTROL_SECTIONS: Array<{ value: ControlSection; label: string }> = [
  { value: 'board', label: 'Board' },
  { value: 'node', label: 'Node' },
  { value: 'focus', label: 'Focus' },
  { value: 'physics', label: 'Physics' },
]

function fallbackNodeTypeStyle(style: GraphStyleConfig): NodeTypeStyle {
  return {
    color: style.nodeColor,
    size: style.nodeSize,
    shape: 'circle',
    borderColor: style.nodeBorderColor,
    borderWidth: style.nodeBorderWidth,
  }
}

export function SettingsPanel(props: SettingsPanelProps) {
  const {
    style,
    layout,
    nodeTypes,
    presetNames,
    onStyleChange,
    onLayoutChange,
    onPresetChange,
    onPresetAdd,
    onPresetRemove,
    onPresetSave,
  } = props
  const [draftLayout, setDraftLayout] = useState(layout)
  const [activeControl, setActiveControl] = useState<ControlSection>('board')
  const [selectedNodeType, setSelectedNodeType] = useState<string>('')
  const effectiveNodeType = nodeTypes.includes(selectedNodeType) ? selectedNodeType : (nodeTypes[0] ?? '')
  const effectiveNodeTypeStyle = effectiveNodeType
    ? (style.nodeTypeStyles?.[effectiveNodeType] ?? fallbackNodeTypeStyle(style))
    : fallbackNodeTypeStyle(style)

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
          ...effectiveNodeTypeStyle,
          ...patch,
        },
      },
    })
  }

  const addPreset = (): void => {
    const presetName = window.prompt('Preset name')
    const trimmedPresetName = presetName?.trim()
    if (!trimmedPresetName) {
      return
    }
    if (presetNames.includes(trimmedPresetName)) {
      window.alert('Preset name already exists.')
      return
    }
    onPresetAdd(trimmedPresetName)
  }

  const renderControlPanel = () => {
    if (activeControl === 'board') {
      return (
        <>
          <h3>Board</h3>
          <div className="split-row">
            <label>
              Background
              <input
                type="color"
                value={style.backgroundColor}
                onChange={(event) => onStyleChange({ ...style, backgroundColor: event.target.value })}
              />
            </label>
            <label>
              Node color
              <input
                type="color"
                value={style.nodeColor}
                onChange={(event) => onStyleChange({ ...style, nodeColor: event.target.value })}
              />
            </label>
          </div>
          <div className="split-row">
            <label>
              Edge color
              <input
                type="color"
                value={style.edgeColor}
                onChange={(event) => onStyleChange({ ...style, edgeColor: event.target.value })}
              />
            </label>
            <label>
              Node size
              <span className="control-value">{style.nodeSize}</span>
              <input
                type="range"
                min={2}
                max={20}
                value={style.nodeSize}
                onChange={(event) => onStyleChange({ ...style, nodeSize: Number(event.target.value) })}
              />
            </label>
          </div>
          <div className="split-row">
            <label>
              Edge width
              <span className="control-value">{style.edgeWidth}</span>
              <input
                type="range"
                min={0.2}
                max={6}
                step={0.1}
                value={style.edgeWidth}
                onChange={(event) => onStyleChange({ ...style, edgeWidth: Number(event.target.value) })}
              />
            </label>
          </div>
        </>
      )
    }

    if (activeControl === 'node') {
      return (
        <>
          <h3>Node Type Design</h3>
          {nodeTypes.length === 0 ? (
            <p className="muted-copy">Load graph data to edit node type styles.</p>
          ) : (
            <>
              <div className="split-row">
                <label>
                  Node type
                  <select value={effectiveNodeType} onChange={(event) => setSelectedNodeType(event.target.value)}>
                    {nodeTypes.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Shape
                  <select
                    value={effectiveNodeTypeStyle.shape}
                    onChange={(event) => updateNodeTypeStyle({ shape: event.target.value as NodeShape })}
                  >
                    {NODE_SHAPES.map((shape) => (
                      <option key={shape} value={shape}>{shape}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="split-row">
                <label>
                  Type color
                  <input
                    type="color"
                    value={effectiveNodeTypeStyle.color}
                    onChange={(event) => updateNodeTypeStyle({ color: event.target.value })}
                  />
                </label>
                <label>
                  Border color
                  <input
                    type="color"
                    value={effectiveNodeTypeStyle.borderColor}
                    onChange={(event) => updateNodeTypeStyle({ borderColor: event.target.value })}
                  />
                </label>
              </div>
              <div className="split-row">
                <label>
                  Type size
                  <span className="control-value">{effectiveNodeTypeStyle.size}</span>
                  <input
                    type="range"
                    min={2}
                    max={24}
                    step={0.2}
                    value={effectiveNodeTypeStyle.size}
                    onChange={(event) => updateNodeTypeStyle({ size: Number(event.target.value) })}
                  />
                </label>
                <label>
                  Border width
                  <span className="control-value">{effectiveNodeTypeStyle.borderWidth}</span>
                  <input
                    type="range"
                    min={0}
                    max={5}
                    step={0.1}
                    value={effectiveNodeTypeStyle.borderWidth}
                    onChange={(event) => updateNodeTypeStyle({ borderWidth: Number(event.target.value) })}
                  />
                </label>
              </div>
            </>
          )}
        </>
      )
    }

    if (activeControl === 'focus') {
      return (
        <>
          <h3>Focus & Labels</h3>
          <div className="split-row">
            <label>
              Hover color
              <input
                type="color"
                value={style.hoverColor}
                onChange={(event) => onStyleChange({ ...style, hoverColor: event.target.value })}
              />
            </label>
            <label>
              Selected color
              <input
                type="color"
                value={style.selectedColor}
                onChange={(event) => onStyleChange({ ...style, selectedColor: event.target.value })}
              />
            </label>
          </div>
          <div className="split-row">
            <label>
              Highlight color
              <input
                type="color"
                value={style.highlightedColor}
                onChange={(event) => onStyleChange({ ...style, highlightedColor: event.target.value })}
              />
            </label>
            <label>
              Label size
              <input
                type="number"
                min={8}
                max={22}
                value={style.labelFontSize}
                onChange={(event) => onStyleChange({ ...style, labelFontSize: Number(event.target.value) })}
              />
            </label>
            <label>
              Max label length
              <input
                type="number"
                min={8}
                max={80}
                value={style.maxLabelLength}
                onChange={(event) => onStyleChange({ ...style, maxLabelLength: Number(event.target.value) })}
              />
            </label>
          </div>
          <div className="toggle-grid">
            <label className="check-row">
              <input
                type="checkbox"
                checked={style.arrowVisibility}
                onChange={(event) => onStyleChange({ ...style, arrowVisibility: event.target.checked })}
              />
              Show arrows
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={style.labelVisible}
                onChange={(event) => onStyleChange({ ...style, labelVisible: event.target.checked })}
              />
              Show labels
            </label>
          </div>
        </>
      )
    }

    return (
      <>
        <h3>Force Layout</h3>
        <div className="split-row">
          <label>
            Link distance
            <span className="control-value">{draftLayout.linkDistance}</span>
            <input
              type="range"
              min={20}
              max={320}
              value={draftLayout.linkDistance}
              onChange={(event) => setDraftLayout({ ...draftLayout, linkDistance: Number(event.target.value) })}
            />
          </label>
          <label>
            Charge / repulsion
            <span className="control-value">{draftLayout.chargeStrength}</span>
            <input
              type="range"
              min={-700}
              max={-10}
              value={draftLayout.chargeStrength}
              onChange={(event) => setDraftLayout({ ...draftLayout, chargeStrength: Number(event.target.value) })}
            />
          </label>
        </div>
        <div className="split-row">
          <label>
            Collision radius
            <span className="control-value">{draftLayout.collisionRadius}</span>
            <input
              type="range"
              min={1}
              max={40}
              value={draftLayout.collisionRadius}
              onChange={(event) => setDraftLayout({ ...draftLayout, collisionRadius: Number(event.target.value) })}
            />
          </label>
          <label>
            Force strength
            <span className="control-value">{draftLayout.alphaDecay.toFixed(3)}</span>
            <input
              type="range"
              min={0.005}
              max={0.08}
              step={0.001}
              value={draftLayout.alphaDecay}
              onChange={(event) => setDraftLayout({ ...draftLayout, alphaDecay: Number(event.target.value) })}
            />
          </label>
        </div>
        <div className="layout-actions">
          <button type="button" className="primary-action" onClick={applyDraftLayout} disabled={!hasDraftLayoutChanges}>
            Apply Layout
          </button>
          <button type="button" onClick={() => setDraftLayout(layout)} disabled={!hasDraftLayoutChanges}>
            Reset Changes
          </button>
        </div>
      </>
    )
  }

  return (
    <section className="settings-panel">
      <div className="settings-header">
        <div>
          <h2>Style & Layout</h2>
          <p>Change the visual language and force layout while watching the graph preview.</p>
        </div>
        <span className="status-badge">{style.presetName}</span>
        <label className="section-control">
          Preset
          <select
            value={presetNames.includes(style.presetName) ? style.presetName : ''}
            onChange={(event) => onPresetChange(event.target.value)}
          >
            {presetNames.includes(style.presetName) ? null : <option value="">Custom</option>}
            {presetNames.map((presetName) => (
              <option key={presetName} value={presetName}>{presetName}</option>
            ))}
          </select>
        </label>
        <div className="preset-sidebar-controls">
          <label>
            Controls
            <select value={activeControl} onChange={(event) => setActiveControl(event.target.value as ControlSection)}>
              {CONTROL_SECTIONS.map((section) => (
                <option key={section.value} value={section.value}>{section.label}</option>
              ))}
            </select>
          </label>
          <div className="action-grid preset-actions">
            <button type="button" onClick={addPreset}>Add Preset</button>
            <button
              type="button"
              onClick={() => onPresetRemove(style.presetName)}
              disabled={!presetNames.includes(style.presetName) || presetNames.length <= 1}
            >
              Remove Preset
            </button>
            <button
              type="button"
              className="primary-action"
              onClick={() => onPresetSave(style.presetName)}
              disabled={!presetNames.includes(style.presetName)}
            >
              Save Preset
            </button>
          </div>
        </div>
      </div>

      <div className="settings-group control-panel">
        {renderControlPanel()}
      </div>
    </section>
  )
}
