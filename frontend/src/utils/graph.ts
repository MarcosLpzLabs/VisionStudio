// Utilidades de grafo: acceso a especificaciones y validación de conexiones.
// La validación en el cliente replica la del backend (docs/CONTRATOS.md §5)
// para dar feedback inmediato antes de guardar el proyecto.

import type {
  BlockCatalog,
  BlockSpec,
  PortSpec,
  Project,
  ProjectConnection,
} from '../types'

export function findBlockSpec(catalog: BlockCatalog | null, type: string): BlockSpec | undefined {
  if (!catalog) return undefined
  for (const specs of Object.values(catalog)) {
    const found = specs.find((spec) => spec.id === type)
    if (found) return found
  }
  return undefined
}

export function findPort(spec: BlockSpec, portId: string, kind: 'input' | 'output'): PortSpec | undefined {
  const ports = kind === 'input' ? spec.inputs : spec.outputs
  return ports.find((port) => port.id === portId)
}

export function defaultParams(spec: BlockSpec): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  for (const param of spec.params) {
    params[param.id] = Array.isArray(param.default) ? [...param.default] : param.default
  }
  return params
}

export function newBlockId(type: string, project: Project): string {
  // Id único dentro del proyecto: prefijo del tipo + contador aleatorio.
  const used = new Set(project.blocks.map((b) => b.id))
  let id = ''
  do {
    id = `${type.replace('block.', '')}-${Math.random().toString(36).slice(2, 8)}`
  } while (used.has(id))
  return id
}

export function connectionKey(connection: ProjectConnection): string {
  return `${connection.from.block}:${connection.from.port}->${connection.to.block}:${connection.to.port}`
}

// --- Validación de una nueva conexión -------------------------------------

export type ConnectionError = 'self' | 'already_connected' | 'type' | 'cycle'

export function validateConnection(
  catalog: BlockCatalog | null,
  project: Project,
  fromBlock: string,
  fromPort: string,
  toBlock: string,
  toPort: string,
): ConnectionError | null {
  // 1) No conectarse consigo mismo.
  if (fromBlock === toBlock) return 'self'

  // 2) Un puerto de entrada solo admite una conexión.
  const occupied = project.connections.some(
    (c) => c.to.block === toBlock && c.to.port === toPort,
  )
  if (occupied) return 'already_connected'

  // 3) Compatibilidad de tipos.
  const fromSpec = findBlockSpec(catalog, fromBlockType(project, fromBlock))
  const toSpec = findBlockSpec(catalog, fromBlockType(project, toBlock))
  if (fromSpec && toSpec) {
    const fromTypes = findPort(fromSpec, fromPort, 'output')?.types ?? []
    const toTypes = findPort(toSpec, toPort, 'input')?.types ?? []
    if (!fromTypes.some((type) => toTypes.includes(type))) return 'type'
  }

  // 4) El grafo debe seguir siendo un DAG (no crear ciclos).
  if (wouldCreateCycle(project, fromBlock, toBlock)) return 'cycle'

  return null
}

function fromBlockType(project: Project, blockId: string): string {
  return project.blocks.find((b) => b.id === blockId)?.type ?? ''
}

export function wouldCreateCycle(project: Project, fromBlock: string, toBlock: string): boolean {
  // DFS desde `toBlock` buscando llegar a `fromBlock`.
  const adjacency = new Map<string, string[]>()
  for (const connection of project.connections) {
    const list = adjacency.get(connection.from.block) ?? []
    list.push(connection.to.block)
    adjacency.set(connection.from.block, list)
  }
  // Añadir la arista candidata.
  const list = adjacency.get(fromBlock) ?? []
  list.push(toBlock)
  adjacency.set(fromBlock, list)

  const visited = new Set<string>()
  const stack = [toBlock]
  while (stack.length > 0) {
    const current = stack.pop()!
    if (current === fromBlock) return true
    if (visited.has(current)) continue
    visited.add(current)
    for (const next of adjacency.get(current) ?? []) {
      if (!visited.has(next)) stack.push(next)
    }
  }
  return false
}