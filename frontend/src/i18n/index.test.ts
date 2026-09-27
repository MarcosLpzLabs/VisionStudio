// Pruebas del sistema i18n (fase 11, Quality).
// Verifican la interpolación de parámetros, la resolución de `detail` a claves
// conocidas y el respaldo al mensaje genérico, además de la paridad es/en.
import { describe, expect, it } from 'vitest'
import { hasKey, t, translateError } from './index'
import es from './es.json'
import en from './en.json'

describe('t', () => {
  it('interpola los parámetros en la plantilla', () => {
    const text = t('es', 'err.ERR_PORT_ALREADY_CONNECTED', { port_id: 'in' })
    expect(text).toBe('La entrada in ya tiene una conexión.')
  })

  it('devuelve la propia clave si no existe (para detectarla en desarrollo)', () => {
    expect(t('es', 'clave.inexistente')).toBe('clave.inexistente')
  })
})

describe('hasKey', () => {
  it('distingue claves existentes y ausentes', () => {
    expect(hasKey('es', 'err.generic')).toBe(true)
    expect(hasKey('es', 'no.existe')).toBe(false)
  })
})

describe('translateError', () => {
  it('traduce un código conocido', () => {
    expect(translateError('es', 'ERR_GRAPH_CYCLE')).toBe('El grafo contiene un ciclo.')
  })

  it('resuelve `detail` cuando es una clave err.detail.* conocida', () => {
    const text = translateError('es', 'ERR_PARAM_INVALID', { detail: 'kernel_odd' })
    expect(text).toBe('Parámetro inválido: el núcleo debe ser impar y mayor o igual que 1.')
  })

  it('deja intacto un `detail` que es texto técnico libre', () => {
    const text = translateError('es', 'ERR_PARAM_INVALID', { detail: 'str(exc) inesperado' })
    expect(text).toBe('Parámetro inválido: str(exc) inesperado.')
  })

  it('cae al mensaje genérico con el código si no hay traducción', () => {
    expect(translateError('es', 'ERR_DESCONOCIDO')).toBe('Error: ERR_DESCONOCIDO.')
  })
})

describe('catálogos es/en', () => {
  it('tienen exactamente las mismas claves (paridad)', () => {
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort())
  })
})
