import { defineConfig } from 'vitest/config'

// Configuración de Vitest (fase 11).
// Entorno `node`: las pruebas son de lógica pura (grafo, store, i18n), sin DOM.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
