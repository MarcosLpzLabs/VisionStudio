// Sincronización automática del proyecto con el backend.
// Cuando el proyecto del store cambia (y el flujo está detenido) se envía un
// PUT debounced de ~400 ms a /api/project, de modo que "Ejecutar" funcione sin
// pulsar Guardar. Las respuestas obsoletas se ignoran con un contador de
// secuencia y los errores se reportan al panel.
import { useEffect, useRef } from 'react'
import { sendProject } from '../api/client'
import { useAppStore } from '../store/appStore'

export function useAutoSync() {
  const project = useAppStore((state) => state.project)
  const flowState = useAppStore((state) => state.flowState)
  const addError = useAppStore((state) => state.addError)

  // Se omite el render inicial para no sobrescribir el proyecto del servidor
  // con el proyecto vacío justo al arrancar la aplicación.
  const firstRun = useRef(true)
  // Contador de secuencia: solo se notifican errores de la última petición.
  const seqRef = useRef(0)

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false
      return
    }
    // Solo se sincroniza con el flujo detenido (grafo editable).
    if (flowState !== 'stopped') return
    const seq = ++seqRef.current
    const timer = setTimeout(() => {
      sendProject(project).catch((error) => {
        // Respuesta obsoleta: se ignora si ya se lanzó una petición más nueva.
        if (seq === seqRef.current) {
          addError(
            (error as { code?: string }).code ?? 'ERR_INTERNAL',
            (error as { params?: Record<string, unknown> }).params,
          )
        }
      })
    }, 400)
    return () => clearTimeout(timer)
  }, [project, flowState, addError])
}