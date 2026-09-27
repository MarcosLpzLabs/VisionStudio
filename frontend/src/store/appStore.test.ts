// Pruebas del store (fase 11, Quality).
// Cubren las mutaciones del grafo, el historial de deshacer/rehacer (con el
// debounce de cambios continuos) y el bloqueo de la edición en ejecución.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from './appStore'
import type { BlockCatalog, BlockSpec, Project } from '../types'

// --- Fixtures -------------------------------------------------------------

function spec(id: string, inputs: BlockSpec['inputs'], outputs: BlockSpec['outputs']): BlockSpec {
  return {
    id,
    category: 'processing',
    name_key: id,
    description_key: `${id}.desc`,
    inputs,
    outputs,
    params: [],
    behavior: 'continuous',
  }
}

const catalog: BlockCatalog = {
  processing: [
    spec('block.camera', [], [{ id: 'out', label_key: 'out', types: ['frame'], required: false }]),
    spec(
      'block.grayscale',
      [{ id: 'in', label_key: 'in', types: ['frame'], required: true }],
      [{ id: 'out', label_key: 'out', types: ['frame'], required: false }],
    ),
  ],
}

function baseProject(): Project {
  return {
    format_version: 2,
    name: 'test',
    language: 'es',
    camera: { index: 0, width: 640, height: 480 },
    flow: { mode: 'manual', interval_ms: 100 },
    blocks: [],
    connections: [],
  }
}

function resetStore(project: Project = baseProject()): void {
  const store = useAppStore.getState()
  store.setBlocksCatalog(catalog)
  store.setProject(project)
  store.setFlowState('stopped')
  store.setSelectedNodeId(null)
  store.setSelectedEdgeId(null)
}

beforeEach(() => {
  vi.useFakeTimers()
  resetStore()
})

afterEach(() => {
  // Cancela cualquier debounce pendiente antes de restaurar los timers.
  resetStore()
  vi.useRealTimers()
})

// --- addBlock / undo / redo ----------------------------------------------

describe('addBlock, undo y redo', () => {
  it('añade un bloque, lo selecciona y registra un paso de historial', () => {
    useAppStore.getState().addBlock('block.camera', 10, 20)
    const state = useAppStore.getState()
    expect(state.project.blocks).toHaveLength(1)
    expect(state.project.blocks[0].type).toBe('block.camera')
    expect(state.project.blocks[0].width).toBeNull()
    expect(state.selectedNodeId).toBe(state.project.blocks[0].id)
    expect(state.canUndo()).toBe(true)
    expect(state.canRedo()).toBe(false)
  })

  it('undo revierte y redo reaplica', () => {
    const store = useAppStore.getState()
    store.addBlock('block.camera', 0, 0)

    useAppStore.getState().undo()
    expect(useAppStore.getState().project.blocks).toHaveLength(0)
    expect(useAppStore.getState().canRedo()).toBe(true)

    useAppStore.getState().redo()
    expect(useAppStore.getState().project.blocks).toHaveLength(1)
  })

  it('no permite deshacer si el flujo no está detenido', () => {
    const store = useAppStore.getState()
    store.addBlock('block.camera', 0, 0)
    useAppStore.getState().setFlowState('running')

    useAppStore.getState().undo()
    // El grafo es de solo lectura en ejecución: no se deshace.
    expect(useAppStore.getState().project.blocks).toHaveLength(1)
  })
})

// --- updateBlockParams (debounce) ----------------------------------------

describe('updateBlockParams', () => {
  function projectWithBlock(): Project {
    return {
      ...baseProject(),
      blocks: [{ id: 'cam', type: 'block.camera', x: 0, y: 0, width: null, height: null, params: {} }],
    }
  }

  it('agrupa una ráfaga de cambios en un único paso de undo', () => {
    resetStore(projectWithBlock())

    useAppStore.getState().updateBlockParams('cam', { threshold: 10 })
    useAppStore.getState().updateBlockParams('cam', { threshold: 20 })
    // Antes de expirar el debounce aún no hay paso de historial.
    expect(useAppStore.getState().canUndo()).toBe(false)

    vi.advanceTimersByTime(400)
    const state = useAppStore.getState()
    expect(state.canUndo()).toBe(true)
    expect(state.project.blocks[0].params.threshold).toBe(20)

    useAppStore.getState().undo()
    // Un solo deshacer revierte toda la ráfaga.
    expect(useAppStore.getState().project.blocks[0].params.threshold).toBeUndefined()
  })
})

// --- resizeBlock (debounce) ----------------------------------------------

describe('resizeBlock', () => {
  function projectWithBlock(): Project {
    return {
      ...baseProject(),
      blocks: [{ id: 'cam', type: 'block.camera', x: 0, y: 0, width: null, height: null, params: {} }],
    }
  }

  it('redondea el tamaño y lo agrupa en un solo paso de undo', () => {
    resetStore(projectWithBlock())

    useAppStore.getState().resizeBlock('cam', 200.4, 150.6)
    expect(useAppStore.getState().project.blocks[0].width).toBe(200)
    expect(useAppStore.getState().project.blocks[0].height).toBe(151)

    vi.advanceTimersByTime(400)
    useAppStore.getState().undo()
    expect(useAppStore.getState().project.blocks[0].width).toBeNull()
  })
})

// --- removeBlock / removeConnection --------------------------------------

describe('removeBlock y removeConnection', () => {
  function projectWithTwoBlocks(): Project {
    return {
      ...baseProject(),
      blocks: [
        { id: 'cam', type: 'block.camera', x: 0, y: 0, params: {} },
        { id: 'gray', type: 'block.grayscale', x: 100, y: 0, params: {} },
      ],
      connections: [{ from: { block: 'cam', port: 'out' }, to: { block: 'gray', port: 'in' } }],
    }
  }

  it('borra un bloque junto con sus conexiones', () => {
    resetStore(projectWithTwoBlocks())
    useAppStore.getState().removeBlock('gray')
    const state = useAppStore.getState()
    expect(state.project.blocks.map((b) => b.id)).toEqual(['cam'])
    expect(state.project.connections).toHaveLength(0)
  })

  it('borra una conexión individual y limpia su selección', () => {
    resetStore(projectWithTwoBlocks())
    useAppStore.getState().setSelectedEdgeId('cam:out->gray:in')
    useAppStore.getState().removeConnection('cam', 'out', 'gray', 'in')
    const state = useAppStore.getState()
    expect(state.project.connections).toHaveLength(0)
    expect(state.selectedEdgeId).toBeNull()
  })
})

// --- addConnection --------------------------------------------------------

describe('addConnection', () => {
  function projectWithTwoBlocks(): Project {
    return {
      ...baseProject(),
      blocks: [
        { id: 'cam', type: 'block.camera', x: 0, y: 0, params: {} },
        { id: 'gray', type: 'block.grayscale', x: 100, y: 0, params: {} },
      ],
    }
  }

  it('acepta una conexión válida y la registra', () => {
    resetStore(projectWithTwoBlocks())
    const result = useAppStore.getState().addConnection('cam', 'out', 'gray', 'in')
    expect(result.ok).toBe(true)
    expect(useAppStore.getState().project.connections).toHaveLength(1)
  })

  it('rechaza una conexión inválida con un código de error estable', () => {
    resetStore(projectWithTwoBlocks())
    const result = useAppStore.getState().addConnection('cam', 'out', 'cam', 'in')
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('ERR_CONNECTION_TYPE')
    expect(useAppStore.getState().project.connections).toHaveLength(0)
  })
})

// --- límite de historial --------------------------------------------------

describe('límite de historial', () => {
  it('no acumula más de 50 pasos de deshacer', () => {
    for (let i = 0; i < 55; i += 1) {
      useAppStore.getState().addBlock('block.camera', i, 0)
    }
    expect(useAppStore.getState().history).toHaveLength(50)
  })
})
