// Componente raíz de la aplicación.
// Carga el catálogo de bloques, conecta el WebSocket y dispone el layout.
import { useEffect, useRef } from 'react'
import { fetchBlocksCatalog, fetchFlowState } from './api/client'
import { SocketClient } from './api/socket'
import { BlockLibrary } from './components/BlockLibrary'
import { ErrorPanel } from './components/ErrorPanel'
import { FlowCanvas } from './components/FlowCanvas'
import { PropertyPanel } from './components/PropertyPanel'
import { StatusBar } from './components/StatusBar'
import { Toolbar } from './components/Toolbar'
import { useAutoSync } from './hooks/useAutoSync'
import { useShortcuts } from './hooks/useShortcuts'
import { useAppStore } from './store/appStore'
import type { FlowState, WsSinkMessage } from './types'

function useSocket() {
  // Conecta el WebSocket y enruta cada mensaje al store. Reconexión incluida
  // en SocketClient (1s de reintento).
  useEffect(() => {
    const { addError, setFlowState, setConnected, setSinkData } = useAppStore.getState()
    const client = new SocketClient(
      '',
      (message) => {
        if (message.type === 'state') {
          setFlowState(message.state)
        } else if (message.type === 'error') {
          addError(message.code, message.params)
        } else {
          const sink = message as WsSinkMessage
          if (sink.type === 'frame') {
            setSinkData(sink.sink, { kind: 'frame', data: sink.data })
          } else {
            setSinkData(sink.sink, { kind: sink.type, value: sink.value })
          }
        }
      },
      () => setConnected(true),
      () => setConnected(false),
    )
    client.connect()
    return () => client.close()
  }, [])
}

export function App() {
  useSocket()
  useAutoSync()
  useShortcuts()
  const setBlocksCatalog = useAppStore((state) => state.setBlocksCatalog)
  const setFlowState = useAppStore((state) => state.setFlowState)
  const setLanguage = useAppStore((state) => state.setLanguage)
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    // Idioma preferido guardado en el navegador.
    const saved = localStorage.getItem('vs-language')
    if (saved === 'es' || saved === 'en') {
      setLanguage(saved)
    }

    // Catálogo de bloques para la biblioteca y la validación de conexiones.
    fetchBlocksCatalog()
      .then(setBlocksCatalog)
      .catch(() => useAppStore.getState().addError('ERR_INTERNAL', { detail: 'catálogo' }))

    // Estado inicial del flujo en el servidor.
    fetchFlowState()
      .then((state) => setFlowState(state as FlowState))
      .catch(() => undefined)
  }, [setBlocksCatalog, setFlowState, setLanguage])

  return (
    <div className="vs-app">
      <Toolbar />
      <div className="vs-main">
        <BlockLibrary />
        <FlowCanvas />
        <PropertyPanel />
      </div>
      <ErrorPanel />
      <StatusBar />
    </div>
  )
}