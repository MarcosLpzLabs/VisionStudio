// Tipos del frontend (contrato con el backend, docs/CONTRATOS.md).
// No contienen lógica OpenCV: reflejan la API REST y el WebSocket.

export type Language = 'es' | 'en'

export type FlowState = 'stopped' | 'running' | 'paused'

export type BlockCategory = 'source' | 'control' | 'processing' | 'analysis' | 'output'

// --- Especificación de bloques (GET /api/blocks) --------------------------

export interface PortSpec {
  id: string
  label_key: string
  types: string[]
  required: boolean
}

export interface ParamSpec {
  id: string
  label_key: string
  type: 'number' | 'boolean' | 'string' | 'select' | 'color'
  kind?: 'float' | 'int'
  default: unknown
  min?: number
  max?: number
  step?: number
  options?: string[]
  required: boolean
  // Poka-yoke: si es true, el valor entero debe ser impar (p. ej. kernel).
  odd?: boolean
}

export interface BlockSpec {
  id: string
  category: BlockCategory
  name_key: string
  description_key: string
  inputs: PortSpec[]
  outputs: PortSpec[]
  params: ParamSpec[]
  behavior: 'continuous' | 'on_tick' | 'on_trigger' | 'passthrough'
  doc_url?: string
}

export type BlockCatalog = Record<string, BlockSpec[]>

// --- Proyecto (GET/PUT /api/project) --------------------------------------

export interface ProjectBlock {
  id: string
  type: string
  x: number
  y: number
  // Tamaño en el lienzo (formato v2). null/undefined = automático.
  width?: number | null
  height?: number | null
  params: Record<string, unknown>
}

export interface ProjectConnection {
  from: { block: string; port: string }
  to: { block: string; port: string }
}

export interface Project {
  format_version: number
  name: string
  language: Language
  camera: { index: number; width: number; height: number }
  flow: { mode: 'continuous' | 'timer' | 'manual'; interval_ms: number }
  blocks: ProjectBlock[]
  connections: ProjectConnection[]
}

// --- SinkData: valor recibido por un sink vía WebSocket -------------------

export interface SinkData {
  kind: 'frame' | 'text' | 'boolean' | 'status' | 'number' | 'coordinates' | 'rectangle' | 'detections' | 'analysis'
  value?: unknown
  data?: string // base64 JPEG para frame
}

// --- Errores de la aplicación ---------------------------------------------

// Error de la aplicación: código estable + parámetros. El texto se traduce en
// el momento de renderizar (translateError), no se almacena congelado.
export interface AppError {
  code: string
  params?: Record<string, unknown>
}

// --- Mensajes WebSocket ---------------------------------------------------

export interface WsStateMessage {
  type: 'state'
  state: FlowState
}

export interface WsSinkMessage {
  type: 'frame' | 'text' | 'boolean' | 'status' | 'number' | 'coordinates' | 'rectangle' | 'detections' | 'analysis'
  sink: string
  port?: string
  value?: unknown
  data?: string
}

export interface WsErrorMessage {
  type: 'error'
  code: string
  params?: Record<string, unknown>
}

export type WsMessage = WsStateMessage | WsSinkMessage | WsErrorMessage