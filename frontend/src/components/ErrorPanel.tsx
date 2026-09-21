// Panel de errores: lista los errores de la aplicación con su mensaje
// traducido y un botón para limpiar el historial.
import { t, translateError } from '../i18n'
import { useAppStore } from '../store/appStore'

export function ErrorPanel() {
  const { errors, language, clearErrors } = useAppStore()

  return (
    <div className="vs-panel vs-errors">
      <div className="vs-panel-title-row">
        <h3 className="vs-panel-title">{t(language, 'errors.title')}</h3>
        {errors.length > 0 && (
          <button className="vs-small-button" onClick={clearErrors}>
            {t(language, 'errors.clear')}
          </button>
        )}
      </div>
      {errors.length === 0 ? (
        <p className="vs-muted">{t(language, 'errors.empty')}</p>
      ) : (
        <ul className="vs-errors-list">
          {errors.map((error, index) => (
            <li key={`${index}-${error.code}`} className="vs-error-item">
              {/* Se traduce en el render para que el historial siga el idioma. */}
              <span className="vs-error-code">{error.code}</span>{' '}
              {translateError(language, error.code, error.params)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}