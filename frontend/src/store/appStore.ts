// Store global de la aplicación (Zustand).
// Fuente de verdad única del frontend: proyecto, catálogo de bloques, estado
// del flujo, conexión, datos de sinks, errores e historial de deshacer/rehacer.
// No contiene lógica OpenCV.
import { create } from 'zustand'
import type {
  AppError,
  BlockCatalog,
  FlowState,
  Language,
  Project,
  SinkData,
} from '../types'
import { defaultParams, findBlockSpec, newBlockId, validateConnection } from '../utils/graph'

export interface AddConnectionResult {
  ok: boolean
  error?: AppError
}

// Límite de pasos de historial (undo) y de futuro (redo).
const HISTORY_LIMIT = 50
// Tiempo de debounce para agrupar cambios de parámetros en un único paso de undo.
const PARAMS_DEBOUNCE_MS = 400

interface AppStore {
  // idioma e i18n
  language: Language
  setLanguage: (language: Language) => void

  // catálogo de bloques (GET /api/blocks)
  blocksCatalog: BlockCatalog | null
  setBlocksCatalog: (catalog: BlockCatalog) => void

  // proyecto actual (fuente de verdad del grafo)
  project: Project
  setProject: (project: Project) => void
  resetProject: () => void

  // historial de deshacer/rehacer (solo cliente)
  history: Project[]
  future: Project[]
  undo: () => void
  redo: () => void
  canUndo: () => boolean
  canRedo: () => boolean

  // selección en el lienzo (nodo y arista; permiten borrar con Supr)
  selectedNodeId: string | null
  setSelectedNodeId: (id: string | null) => void
  selectedEdgeId: string | null
  setSelectedEdgeId: (id: string | null) => void

  // estado del flujo y conexión
  flowState: FlowState
  setFlowState: (state: FlowState) => void
  connected: boolean
  setConnected: (connected: boolean) => void

  // datos recibidos por los sinks (WebSocket)
  sinkData: Record<string, SinkData>
  setSinkData: (nodeId: string, data: SinkData) => void
  clearSinkData: () => void

  // errores (panel)
  errors: AppError[]
  addError: (code: string, params?: Record<string, unknown>) => void
  clearErrors: () => void

  // mutaciones del grafo
  addBlock: (type: string, x: number, y: number) => void
  removeBlock: (nodeId: string) => void
  moveBlock: (nodeId: string, x: number, y: number) => void
  resizeBlock: (nodeId: string, width: number, height: number) => void
  updateBlockParams: (nodeId: string, params: Record<string, unknown>) => void
  addConnection: (
    fromBlock: string,
    fromPort: string,
    toBlock: string,
    toPort: string,
  ) => AddConnectionResult
  removeConnection: (fromBlock: string, fromPort: string, toBlock: string, toPort: string) => void
}

function emptyProject(language: Language): Project {
  return {
    format_version: 2,
    name: 'Untitled',
    language,
    camera: { index: 0, width: 640, height: 480 },
    flow: { mode: 'continuous', interval_ms: 100 },
    blocks: [],
    connections: [],
  }
}

export const useAppStore = create<AppStore>((set, get) => {
  // Estado del debounce de cambios continuos (parámetros y redimensionado):
  // recuerda el proyecto anterior al grupo para que, al expirar, se registre
  // como un único paso de undo (una ráfaga de escritura = un solo deshacer).
  let pendingTimer: ReturnType<typeof setTimeout> | null = null
  let pendingBeforeProject: Project | null = null

  // Compromete el grupo pendiente de cambios continuos en el historial.
  // Se llama antes de cualquier otra mutación y antes de undo/redo para que el
  // grupo en curso no se pierda.
  const flushPendingDebounce = () => {
    if (pendingTimer === null || pendingBeforeProject === null) return
    clearTimeout(pendingTimer)
    pendingTimer = null
    const { history, future } = get()
    set({ history: [...history, pendingBeforeProject].slice(-HISTORY_LIMIT), future })
    pendingBeforeProject = null
  }

  // Registra `before` como el proyecto deshacible antes de una mutación y
  // limpia el futuro (redo). Devuelve el par history/future para el set.
  const snapshot = (before: Project) => {
    const { history } = get()
    return { history: [...history, before].slice(-HISTORY_LIMIT), future: [] }
  }

  // Cancela cualquier debounce pendiente (para cargas/resets).
  const cancelPendingDebounce = () => {
    if (pendingTimer !== null) {
      clearTimeout(pendingTimer)
      pendingTimer = null
    }
    pendingBeforeProject = null
  }

  return {
    language: 'es',
    setLanguage: (language) => {
      set({ language })
    },

    blocksCatalog: null,
    setBlocksCatalog: (catalog) => set({ blocksCatalog: catalog }),

    project: emptyProject('es'),
    // Carga de proyecto (servidor/archivo): no genera entradas de historial.
    setProject: (project) => {
      cancelPendingDebounce()
      set({ project, history: [], future: [] })
    },
    resetProject: () => {
      cancelPendingDebounce()
      set({ project: emptyProject(get().language), history: [], future: [] })
    },

    history: [],
    future: [],
    undo: () => {
      // Solo se deshace con el flujo detenido (grafo de solo lectura en ejecución).
      if (get().flowState !== 'stopped') return
      // Compromete primero el grupo continuo pendiente.
      flushPendingDebounce()
      const state = get()
      if (state.history.length === 0) return
      const previous = state.history[state.history.length - 1]
      const selectedStillExists = previous.blocks.some((b) => b.id === state.selectedNodeId)
      set({
        project: previous,
        history: state.history.slice(0, -1),
        future: [state.project, ...state.future].slice(0, HISTORY_LIMIT),
        sinkData: {},
        selectedNodeId: selectedStillExists ? state.selectedNodeId : null,
        // El historial puede no contener la arista seleccionada: se limpia.
        selectedEdgeId: null,
      })
    },
    redo: () => {
      if (get().flowState !== 'stopped') return
      const state = get()
      if (state.future.length === 0) return
      const next = state.future[0]
      const selectedStillExists = next.blocks.some((b) => b.id === state.selectedNodeId)
      set({
        project: next,
        history: [...state.history, state.project].slice(-HISTORY_LIMIT),
        future: state.future.slice(1),
        sinkData: {},
        selectedNodeId: selectedStillExists ? state.selectedNodeId : null,
        selectedEdgeId: null,
      })
    },
    canUndo: () => get().history.length > 0,
    canRedo: () => get().future.length > 0,

    selectedNodeId: null,
    setSelectedNodeId: (id) => set({ selectedNodeId: id }),
    selectedEdgeId: null,
    setSelectedEdgeId: (id) => set({ selectedEdgeId: id }),

    flowState: 'stopped',
    setFlowState: (state) => set({ flowState: state }),
    connected: false,
    setConnected: (connected) => set({ connected }),

    sinkData: {},
    setSinkData: (nodeId, data) =>
      set((state) => ({ sinkData: { ...state.sinkData, [nodeId]: data } })),
    clearSinkData: () => set({ sinkData: {} }),

    errors: [],
    addError: (code, params) => {
      // Se guardan código y parámetros: el texto se traduce al renderizar,
      // de modo que el historial cambia de idioma con el selector.
      const error: AppError = { code, params }
      // Se limita el historial para no saturar el panel.
      set((state) => ({ errors: [...state.errors, error].slice(-50) }))
    },
    clearErrors: () => set({ errors: [] }),

    addBlock: (type, x, y) => {
      const state = get()
      flushPendingDebounce()
      const spec = findBlockSpec(state.blocksCatalog, type)
      if (!spec) return
      const id = newBlockId(type, state.project)
      set({
        ...snapshot(state.project),
        project: {
          ...state.project,
          blocks: [
            ...state.project.blocks,
            // width/height null = tamaño automático (el usuario puede ajustarlo).
            { id, type, x, y, width: null, height: null, params: defaultParams(spec) },
          ],
        },
        selectedNodeId: id,
        // Al seleccionar un bloque se deselecciona cualquier arista.
        selectedEdgeId: null,
      })
    },

    removeBlock: (nodeId) => {
      const state = get()
      flushPendingDebounce()
      set({
        ...snapshot(state.project),
        project: {
          ...state.project,
          blocks: state.project.blocks.filter((b) => b.id !== nodeId),
          connections: state.project.connections.filter(
            (c) => c.from.block !== nodeId && c.to.block !== nodeId,
          ),
        },
        selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
        // Las aristas del bloque se eliminan con él: se limpia su selección.
        selectedEdgeId: null,
      })
    },

    moveBlock: (nodeId, x, y) => {
      const state = get()
      // Solo se registra si la posición cambió de verdad (fin de arrastre).
      const current = state.project.blocks.find((b) => b.id === nodeId)
      if (!current || (current.x === x && current.y === y)) return
      flushPendingDebounce()
      set({
        ...snapshot(state.project),
        project: {
          ...state.project,
          blocks: state.project.blocks.map((b) =>
            b.id === nodeId ? { ...b, x, y } : b,
          ),
        },
      })
    },

    resizeBlock: (nodeId, width, height) => {
      const state = get()
      const current = state.project.blocks.find((b) => b.id === nodeId)
      if (!current) return
      // Se redondea para no guardar decimales de píxeles.
      const w = Math.round(width)
      const h = Math.round(height)
      if (current.width === w && current.height === h) return
      // Igual que los parámetros: una ráfaga de resize = un único paso de undo.
      if (pendingTimer === null) {
        pendingBeforeProject = state.project
      }
      const nextProject = {
        ...state.project,
        blocks: state.project.blocks.map((b) =>
          b.id === nodeId ? { ...b, width: w, height: h } : b,
        ),
      }
      set({ project: nextProject, future: [] })
      if (pendingTimer !== null) clearTimeout(pendingTimer)
      pendingTimer = setTimeout(() => {
        flushPendingDebounce()
      }, PARAMS_DEBOUNCE_MS)
    },

    updateBlockParams: (nodeId, params) => {
      const state = get()
      // Inicio de un grupo: recuerda el proyecto antes del primer cambio para
      // que todo el grupo sea un único paso de undo al expirar el debounce.
      if (pendingTimer === null) {
        pendingBeforeProject = state.project
      }
      // Aplica el cambio al instante para que la UI responda en vivo.
      const nextProject = {
        ...state.project,
        blocks: state.project.blocks.map((b) =>
          b.id === nodeId ? { ...b, params: { ...b.params, ...params } } : b,
        ),
      }
      // Mientras el grupo esté pendiente se limpia el redo (nuevo historial).
      set({ project: nextProject, future: [] })
      if (pendingTimer !== null) clearTimeout(pendingTimer)
      pendingTimer = setTimeout(() => {
        flushPendingDebounce()
      }, PARAMS_DEBOUNCE_MS)
    },

    addConnection: (fromBlock, fromPort, toBlock, toPort) => {
      const state = get()
      const errorKind = validateConnection(
        state.blocksCatalog,
        state.project,
        fromBlock,
        fromPort,
        toBlock,
        toPort,
      )
      if (errorKind !== null) {
        // Traduce la causa a un código de error estable del backend.
        const code =
          errorKind === 'self'
            ? 'ERR_CONNECTION_TYPE'
            : errorKind === 'already_connected'
              ? 'ERR_PORT_ALREADY_CONNECTED'
              : errorKind === 'type'
                ? 'ERR_CONNECTION_TYPE'
                : 'ERR_GRAPH_CYCLE'
        return {
          ok: false,
          // Solo código + parámetros; el texto se traduce al mostrarlo.
          error: { code, params: { to_block: toBlock, to_port: toPort } },
        }
      }
      flushPendingDebounce()
      set({
        ...snapshot(state.project),
        project: {
          ...state.project,
          connections: [
            ...state.project.connections,
            { from: { block: fromBlock, port: fromPort }, to: { block: toBlock, port: toPort } },
          ],
        },
      })
      return { ok: true }
    },

    removeConnection: (fromBlock, fromPort, toBlock, toPort) => {
      const state = get()
      flushPendingDebounce()
      set({
        ...snapshot(state.project),
        project: {
          ...state.project,
          connections: state.project.connections.filter(
            (c) =>
              !(
                c.from.block === fromBlock &&
                c.from.port === fromPort &&
                c.to.block === toBlock &&
                c.to.port === toPort
              ),
          ),
        },
        // La arista borrada deja de existir: se limpia su selección.
        selectedEdgeId: null,
      })
    },
  }
})