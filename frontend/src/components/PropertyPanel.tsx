// Panel de propiedades del bloque seleccionado.
// Muestra la descripción y los parámetros editables según su tipo
// (número, booleano, texto, select, color).
import { useEffect, useState } from 'react'
import { t } from '../i18n'
import { useAppStore } from '../store/appStore'
import { findBlockSpec } from '../utils/graph'
import type { ParamSpec } from '../types'

// Color: el backend usa tuplas BGR; el input HTML usa #rrggbb (RGB).
function bgrToHex(value: unknown): string {
  const arr = Array.isArray(value) ? value : [0, 0, 0]
  const [b, g, r] = arr.map((v) => Number(v) || 0)
  const hex = (n: number) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0')
  return `#${hex(r)}${hex(g)}${hex(b)}`
}

function hexToBgr(hex: string): number[] {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return [b, g, r]
}

// Poka-yoke de paridad: si el parámetro exige impares (p. ej. kernel), un
// valor par se ajusta al impar más cercano dentro de los límites.
function snapOdd(param: ParamSpec, num: number): number {
  if (!param.odd || param.kind !== 'int' || num % 2 !== 0) return num
  const up = num + 1
  const down = num - 1
  // Se prefiere subir, salvo que supere el máximo.
  if (param.max === undefined || up <= param.max) return up
  return down
}

// Entrada numérica con estado de texto local: permite teclear con comodidad
// (p. ej. "21") mientras se normaliza el valor (impar) que se guarda.
function NumberParamInput({
  param,
  value,
  onChange,
  disabled,
}: {
  param: ParamSpec
  value: unknown
  onChange: (value: unknown) => void
  disabled: boolean
}) {
  const [text, setText] = useState(value === undefined || value === null ? '' : String(value))
  const [focused, setFocused] = useState(false)

  // Sincroniza el texto con el valor externo (undo, cargar, etc.) salvo mientras
  // el usuario escribe, para no pisar lo tecleado.
  useEffect(() => {
    if (!focused) setText(value === undefined || value === null ? '' : String(value))
  }, [value, focused])

  const commit = (raw: string) => {
    const num = param.kind === 'int' ? parseInt(raw, 10) : parseFloat(raw)
    if (Number.isNaN(num)) {
      onChange('')
      return
    }
    onChange(snapOdd(param, num))
  }

  return (
    <input
      type="number"
      value={text}
      min={param.min}
      max={param.max}
      step={param.step ?? (param.odd ? 2 : param.kind === 'int' ? 1 : 'any')}
      disabled={disabled}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onChange={(event) => {
        setText(event.target.value)
        commit(event.target.value)
      }}
    />
  )
}

function ParamInput({
  param,
  value,
  onChange,
  disabled,
}: {
  param: ParamSpec
  value: unknown
  onChange: (value: unknown) => void
  disabled: boolean
}) {
  switch (param.type) {
    case 'boolean':
      return (
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
      )
    case 'select':
      return (
        <select
          value={String(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {(param.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      )
    case 'color':
      return (
        <input
          type="color"
          value={bgrToHex(value)}
          disabled={disabled}
          onChange={(event) => onChange(hexToBgr(event.target.value))}
        />
      )
    case 'number':
      return (
        <NumberParamInput
          param={param}
          value={value}
          onChange={onChange}
          disabled={disabled}
        />
      )
    default:
      return (
        <input
          type="text"
          value={value === undefined || value === null ? '' : String(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      )
  }
}

export function PropertyPanel() {
  const { selectedNodeId, project, blocksCatalog, language, updateBlockParams } = useAppStore()
  const block = project.blocks.find((b) => b.id === selectedNodeId)
  const spec = block ? findBlockSpec(blocksCatalog, block.type) : undefined
  const flowState = useAppStore((state) => state.flowState)
  const removeBlock = useAppStore((state) => state.removeBlock)
  // En ejecución, los parámetros no se pueden editar (grafo de solo lectura).
  const editingLocked = flowState !== 'stopped'

  return (
    <aside className="vs-panel vs-properties">
      <h3 className="vs-panel-title">{t(language, 'properties.title')}</h3>
      {!block || !spec ? (
        <p className="vs-muted">{t(language, 'properties.empty')}</p>
      ) : (
        <>
          <h4 className="vs-node-name">{t(language, spec.name_key)}</h4>
          <p className="vs-muted">{t(language, spec.description_key)}</p>
          {spec.params.length === 0 && (
            <p className="vs-muted">{t(language, 'properties.no_params')}</p>
          )}
          {spec.params.map((param) => (
            <label key={param.id} className="vs-param">
              <span className="vs-param-label">{t(language, param.label_key)}</span>
              <ParamInput
                param={param}
                value={block.params[param.id]}
                disabled={editingLocked}
                onChange={(value) =>
                  updateBlockParams(block.id, { [param.id]: value })
                }
              />
            </label>
          ))}
          {!editingLocked && (
            <button
              className="vs-small-button vs-danger-button"
              onClick={() => removeBlock(block.id)}
            >
              {t(language, 'properties.delete_block')}
            </button>
          )}
        </>
      )}
    </aside>
  )
}