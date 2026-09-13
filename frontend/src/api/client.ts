// Cliente REST de la API (docs/ARQUITECTURA.md §6).
// En desarrollo Vite reenvía /api al backend; en producción se sirve desde el
// mismo origen, por lo que no hace falta URL base.
import type { Project, BlockCatalog } from '../types'

export class ApiError extends Error {
  code: string
  params?: Record<string, unknown>

  constructor(code: string, params?: Record<string, unknown>, message?: string) {
    super(message ?? code)
    this.code = code
    this.params = params
  }
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    // El backend devuelve {code, params} en los errores controlados (EngineError).
    const body = (await response.json().catch(() => null)) as
      | { code?: string; params?: Record<string, unknown> }
      | null
    throw new ApiError(body?.code ?? 'ERR_INTERNAL', body?.params)
  }
  return (await response.json()) as T
}

export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path))
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

// --- Métodos de dominio ---------------------------------------------------

export async function fetchBlocksCatalog(): Promise<BlockCatalog> {
  const data = await apiGet<{ categories: BlockCatalog }>('/api/blocks')
  return data.categories
}

export async function fetchProject(): Promise<Project> {
  return apiGet<Project>('/api/project')
}

export async function sendProject(project: Project): Promise<void> {
  await apiPut('/api/project', project)
}

export async function fetchFlowState(): Promise<string> {
  const data = await apiGet<{ state: string }>('/api/state')
  return data.state
}

export async function runCommand(command: 'start' | 'stop' | 'pause' | 'resume' | 'step'): Promise<string> {
  const data = await apiPost<{ state: string }>(`/api/run/${command}`)
  return data.state
}