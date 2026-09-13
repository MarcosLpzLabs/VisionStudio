// Barra de estado inferior: indicador de conexión con el backend y estado
// del flujo (detenido / en ejecución / pausado).
import { t } from '../i18n'
import { useAppStore } from '../store/appStore'

export function StatusBar() {
  const { connected, flowState, language } = useAppStore()

  return (
    <footer className="vs-statusbar">
      <span className={`vs-status-dot ${connected ? 'is-online' : 'is-offline'}`} />
      <span>{t(language, connected ? 'status.connected' : 'status.disconnected')}</span>
      <span className="vs-status-sep">|</span>
      <span>
        {t(language, 'status.state')}: {t(language, `state.${flowState}`)}
      </span>
      <span className="vs-status-spacer" />
      <span className="vs-muted">{t(language, 'app.title')}</span>
    </footer>
  )
}