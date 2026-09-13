// Barra de herramientas superior: control de ejecución, guardar/cargar,
// descargar/subir proyecto y selector de idioma.
import { useRef } from 'react'
import { runCommand, sendProject, fetchProject } from '../api/client'
import { t } from '../i18n'
import { useAppStore } from '../store/appStore'
import type { FlowState, Language } from '../types'

function useRunButton() {
  // Atajo común: sincroniza el proyecto (autosync) antes de arrancar o hacer
  // un paso para que el backend ejecute exactamente el lienzo, actualiza el
  // estado local y añade el error al panel si el backend lo rechaza.
  return async (command: 'start' | 'stop' | 'pause' | 'resume' | 'step') => {
    const state = useAppStore.getState()
    const { addError, setFlowState } = state
    try {
      if (command === 'start' || command === 'step') {
        await sendProject(state.project)
      }
      const next = await runCommand(command)
      setFlowState(next as FlowState)
    } catch (error) {
      addError((error as { code?: string }).code ?? 'ERR_INTERNAL', (error as { params?: Record<string, unknown> }).params)
    }
  }
}

export function Toolbar() {
  const { flowState, language, setLanguage, project } = useAppStore()
  const { addError } = useAppStore()
  const history = useAppStore((state) => state.history)
  const future = useAppStore((state) => state.future)
  const undo = useAppStore((state) => state.undo)
  const redo = useAppStore((state) => state.redo)
  const run = useRunButton()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const editingLocked = flowState !== 'stopped'
  const canUndo = history.length > 0
  const canRedo = future.length > 0

  const handleSave = async () => {
    try {
      await sendProject(project)
    } catch (error) {
      addError((error as { code?: string }).code ?? 'ERR_INTERNAL', (error as { params?: Record<string, unknown> }).params)
    }
  }

  const handleLoad = async () => {
    try {
      const loaded = await fetchProject()
      useAppStore.getState().setProject(loaded)
      useAppStore.getState().clearSinkData()
    } catch (error) {
      addError((error as { code?: string }).code ?? 'ERR_INTERNAL', (error as { params?: Record<string, unknown> }).params)
    }
  }

  const handleNew = () => {
    useAppStore.getState().resetProject()
    useAppStore.getState().clearSinkData()
  }

  const handleDownload = () => {
    // Descarga el proyecto actual como archivo JSON (formato v1).
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${project.name || 'proyecto'}.vsproj.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleUpload = async (file: File | undefined) => {
    if (!file) return
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      useAppStore.getState().setProject(parsed)
      useAppStore.getState().clearSinkData()
      await sendProject(parsed)
    } catch {
      addError('ERR_INTERNAL', { detail: 'Proyecto no válido' })
    }
  }

  return (
    <header className="vs-toolbar">
      <div className="vs-toolbar-group">
        <button disabled={editingLocked} onClick={() => run('start')} title={t(language, 'run.start')}>
          ▶ {t(language, 'run.start')}
        </button>
        <button disabled={flowState === 'stopped'} onClick={() => run('stop')} title={t(language, 'run.stop')}>
          ■ {t(language, 'run.stop')}
        </button>
        <button disabled={flowState !== 'running'} onClick={() => run('pause')} title={t(language, 'run.pause')}>
          ⏸ {t(language, 'run.pause')}
        </button>
        <button disabled={flowState !== 'paused'} onClick={() => run('resume')} title={t(language, 'run.resume')}>
          ▶ {t(language, 'run.resume')}
        </button>
        <button disabled={flowState === 'running'} onClick={() => run('step')} title={t(language, 'run.step')}>
          ⏭ {t(language, 'run.step')}
        </button>
      </div>

      <div className="vs-toolbar-group">
        <button disabled={editingLocked || !canUndo} onClick={undo} title={t(language, 'project.undo')}>
          ⤺ {t(language, 'project.undo')}
        </button>
        <button disabled={editingLocked || !canRedo} onClick={redo} title={t(language, 'project.redo')}>
          ⤻ {t(language, 'project.redo')}
        </button>
      </div>

      <div className="vs-toolbar-group">
        <button onClick={handleSave}>{t(language, 'project.save')}</button>
        <button onClick={handleLoad}>{t(language, 'project.load')}</button>
        <button onClick={handleNew}>{t(language, 'project.new')}</button>
        <button onClick={handleDownload}>{t(language, 'project.download')}</button>
        <button onClick={() => fileInputRef.current?.click()}>{t(language, 'project.upload')}</button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.vsproj.json"
          style={{ display: 'none' }}
          onChange={(event) => handleUpload(event.target.files?.[0])}
        />
      </div>

      <div className="vs-toolbar-group">
        <label>
          {t(language, 'language.label')}:{' '}
          <select
            value={language}
            onChange={(event) => {
              const lang = event.target.value as Language
              setLanguage(lang)
              localStorage.setItem('vs-language', lang)
            }}
          >
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>
        </label>
      </div>
    </header>
  )
}