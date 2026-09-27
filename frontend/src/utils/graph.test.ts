// Pruebas de las utilidades de grafo (fase 11, Quality).
// Verifican la validación de conexiones en cliente, que replica la del backend
// (docs/CONTRATOS.md §5): auto-conexión, entrada única, tipos y ciclos.
import { describe, expect, it } from 'vitest'
import {
  connectionKey,
  defaultParams,
  findBlockSpec,
  findPort,
  newBlockId,
  validateConnection,
  wouldCreateCycle,
} from './graph'
import type { BlockCatalog, BlockSpec, PortSpec, Project } from '../types'

// --- Constructores de fixtures -------------------------------------------

function port(id: string, types: string[], required = false): PortSpec {
  return { id, label_key: `port.${id}`, types, required }
}

function spec(id: string, category: BlockSpec['category'], inputs: PortSpec[], outputs: PortSpec[]): BlockSpec {
  return {
    id,
    category,
    name_key: `block.${id}`,
    description_key: `block.${id}.desc`,
    inputs,
    outputs,
    params: [],
    behavior: 'continuous',
  }
}

const catalog: BlockCatalog = {
  source: [spec('block.camera', 'source', [], [port('out', ['frame'])])],
  processing: [spec('block.grayscale', 'processing', [port('in', ['frame'], true)], [port('out', ['frame'])])],
  analysis: [spec('block.compare', 'analysis', [port('in', ['number'], true)], [port('out', ['boolean'])])],
  output: [spec('block.sink_boolean', 'output', [port('in', ['boolean'], true)], [])],
}

function project(
  blocks: Project['blocks'],
  connections: Project['connections'] = [],
): Project {
  return {
    format_version: 2,
    name: 'test',
    language: 'es',
    camera: { index: 0, width: 640, height: 480 },
    flow: { mode: 'manual', interval_ms: 100 },
    blocks,
    connections,
  }
}

function block(id: string, type: string): Project['blocks'][number] {
  return { id, type, x: 0, y: 0, params: {} }
}

// --- findBlockSpec / findPort --------------------------------------------

describe('findBlockSpec / findPort', () => {
  it('encuentra un bloque por id en cualquier categoría', () => {
    expect(findBlockSpec(catalog, 'block.compare')?.id).toBe('block.compare')
    expect(findBlockSpec(catalog, 'block.inexistente')).toBeUndefined()
    expect(findBlockSpec(null, 'block.compare')).toBeUndefined()
  })

  it('encuentra puertos por id y tipo', () => {
    const camera = findBlockSpec(catalog, 'block.camera')!
    expect(findPort(camera, 'out', 'output')?.types).toEqual(['frame'])
    expect(findPort(camera, 'out', 'input')).toBeUndefined()
  })
})

// --- defaultParams --------------------------------------------------------

describe('defaultParams', () => {
  it('copia los defaults y clona los arrays', () => {
    const withParams: BlockSpec = {
      ...spec('block.x', 'analysis', [], []),
      params: [
        { id: 'n', label_key: 'p.n', type: 'number', default: 5, required: false },
        { id: 'c', label_key: 'p.c', type: 'color', default: [0, 255, 0], required: false },
      ],
    }
    const params = defaultParams(withParams)
    expect(params).toEqual({ n: 5, c: [0, 255, 0] })
    // El array debe ser una copia (mutarlo no afecta al spec).
    ;(params.c as number[]).push(1)
    expect(withParams.params[1].default).toEqual([0, 255, 0])
  })
})

// --- newBlockId -----------------------------------------------------------

describe('newBlockId', () => {
  it('genera ids únicos con prefijo del tipo', () => {
    const p = project([block('camera-abc', 'block.camera')])
    const id = newBlockId('block.camera', p)
    expect(id.startsWith('camera-')).toBe(true)
    expect(p.blocks.map((b) => b.id)).not.toContain(id)
  })
})

// --- connectionKey --------------------------------------------------------

describe('connectionKey', () => {
  it('construye una clave estable con los cuatro extremos', () => {
    expect(
      connectionKey({ from: { block: 'a', port: 'out' }, to: { block: 'b', port: 'in' } }),
    ).toBe('a:out->b:in')
  })
})

// --- validateConnection ---------------------------------------------------

describe('validateConnection', () => {
  const base = project([
    block('cam', 'block.camera'),
    block('gray', 'block.grayscale'),
    block('cmp', 'block.compare'),
  ])

  it('rechaza la auto-conexión', () => {
    expect(validateConnection(catalog, base, 'cam', 'out', 'cam', 'in')).toBe('self')
  })

  it('rechaza un puerto de entrada ya ocupado', () => {
    const p = project(base.blocks, [
      { from: { block: 'cam', port: 'out' }, to: { block: 'gray', port: 'in' } },
    ])
    expect(validateConnection(catalog, p, 'cam', 'out', 'gray', 'in')).toBe('already_connected')
  })

  it('rechaza tipos incompatibles', () => {
    // number (compare.out) -> frame (gray.in)
    expect(validateConnection(catalog, base, 'cmp', 'out', 'gray', 'in')).toBe('type')
  })

  it('rechaza conexiones que crean un ciclo', () => {
    // g1 -> g2 y la candidata g2 -> g1 (tipos compatibles: frame/frame).
    const p = project(
      [block('g1', 'block.grayscale'), block('g2', 'block.grayscale')],
      [{ from: { block: 'g1', port: 'out' }, to: { block: 'g2', port: 'in' } }],
    )
    expect(validateConnection(catalog, p, 'g2', 'out', 'g1', 'in')).toBe('cycle')
  })

  it('acepta una conexión válida', () => {
    expect(validateConnection(catalog, base, 'cam', 'out', 'gray', 'in')).toBeNull()
  })
})

// --- wouldCreateCycle -----------------------------------------------------

describe('wouldCreateCycle', () => {
  it('detecta el ciclo en cadena A -> B -> C y candidata C -> A', () => {
    const p = project(
      [block('a', 'block.camera'), block('b', 'block.grayscale'), block('c', 'block.grayscale')],
      [
        { from: { block: 'a', port: 'out' }, to: { block: 'b', port: 'in' } },
        { from: { block: 'b', port: 'out' }, to: { block: 'c', port: 'in' } },
      ],
    )
    expect(wouldCreateCycle(p, 'c', 'a')).toBe(true)
  })

  it('no marca ciclo si no lo hay', () => {
    const p = project([block('a', 'block.camera'), block('b', 'block.grayscale')])
    expect(wouldCreateCycle(p, 'a', 'b')).toBe(false)
  })
})
