// Biblioteca lateral de bloques agrupados por categoría.
// Los elementos son arrastrables al lienzo (HTML5 drag & drop).
import { t } from '../i18n'
import { useAppStore } from '../store/appStore'
import type { BlockCategory } from '../types'

const CATEGORY_ORDER: BlockCategory[] = ['source', 'control', 'processing', 'analysis', 'output']

export function BlockLibrary() {
  const { blocksCatalog, language } = useAppStore()

  return (
    <aside className="vs-panel vs-library">
      <h3 className="vs-panel-title">{t(language, 'library.title')}</h3>
      {CATEGORY_ORDER.map((category) => (
        <section key={category} className="vs-library-category">
          <h4 className="vs-library-category-title">{t(language, `category.${category}`)}</h4>
          {(blocksCatalog?.[category] ?? []).map((spec) => (
            <div
              key={spec.id}
              className="vs-library-item"
              draggable
              title={t(language, spec.description_key)}
              onDragStart={(event) => {
                // El tipo de bloque se transporta en el dataTransfer.
                event.dataTransfer.setData('application/vs-block', spec.id)
                event.dataTransfer.effectAllowed = 'copy'
              }}
            >
              {t(language, spec.name_key)}
            </div>
          ))}
        </section>
      ))}
    </aside>
  )
}