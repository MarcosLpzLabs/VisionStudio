// Sistema de traducciones (es/en).
// Todo texto visible de la interfaz se obtiene con `t(lang, key, params)`.
// Las claves son estables y coinciden con los contratos del backend.
import es from './es.json'
import en from './en.json'
import type { Language } from '../types'

const catalogs: Record<Language, Record<string, string>> = { es, en }

// Sustituye {token} por el parámetro correspondiente del objeto `params`.
export function t(lang: Language, key: string, params?: Record<string, unknown>): string {
  const catalog = catalogs[lang] ?? catalogs.es
  let text = catalog[key]
  if (text === undefined) {
    // Clave desconocida: se muestra la propia clave para detectarla en desarrollo.
    return key
  }
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.split(`{${name}}`).join(String(value ?? ''))
    }
  }
  return text
}