// Atajos de teclado globales de deshacer/rehacer.
// Ctrl+Z deshace; Ctrl+Shift+Z o Ctrl+Y rehacen. Se omiten si el flujo está
// en ejecución (el grafo es de solo lectura) o si el foco está en un campo.
import { useEffect } from 'react'
import { useAppStore } from '../store/appStore'

export function useShortcuts() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const { flowState, undo, redo } = useAppStore.getState()
      if (flowState !== 'stopped') return
      const mod = event.ctrlKey || event.metaKey
      if (!mod) return
      const key = event.key.toLowerCase()
      if (key === 'z') {
        event.preventDefault()
        if (event.shiftKey) {
          redo()
        } else {
          undo()
        }
      } else if (key === 'y') {
        event.preventDefault()
        redo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}