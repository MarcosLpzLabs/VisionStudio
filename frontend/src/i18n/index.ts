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

// Indica si una clave existe en el catálogo del idioma (con respaldo a `es`).
// Se usa para decidir entre la clave concreta y el mensaje genérico de error.
export function hasKey(lang: Language, key: string): boolean {
  const catalog = catalogs[lang] ?? catalogs.es
  return catalog[key] !== undefined
}

// Resuelve los parámetros de un error antes de formatearlo: si `detail` es un
// código conocido del backend (`err.detail.<detail>`), se sustituye por su
// texto traducido; si no (texto técnico libre), se deja tal cual.
function resolveErrorParams(
  lang: Language,
  params?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (!params || typeof params.detail !== 'string') return params
  const detailKey = `err.detail.${params.detail}`
  if (!hasKey(lang, detailKey)) return params
  return { ...params, detail: t(lang, detailKey) }
}

// Traduce un error del backend a partir de su código estable y sus parámetros.
// Si el código no tiene traducción, cae al mensaje genérico con el propio código.
export function translateError(
  lang: Language,
  code: string,
  params?: Record<string, unknown>,
): string {
  const resolved = resolveErrorParams(lang, params)
  if (hasKey(lang, `err.${code}`)) {
    return t(lang, `err.${code}`, resolved)
  }
  return t(lang, 'err.generic', { ...(resolved ?? {}), code })
}
