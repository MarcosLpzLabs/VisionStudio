// Nodo de bloque personalizado de React Flow.
// Muestra el nombre del bloque (traducido), sus puertos de entrada/salida y,
// en los sinks, el valor o imagen recibidos en tiempo real por WebSocket.
import { Handle, NodeResizer, Position, type Node, type NodeProps } from '@xyflow/react'
import { t } from '../i18n'
import { useAppStore } from '../store/appStore'
import type { BlockSpec, Language, PortSpec } from '../types'
import { findBlockSpec } from '../utils/graph'

export type BlockNodeData = {
  blockType: string
}

function SinkContent({ nodeId }: { nodeId: string }) {
  const { sinkData, language } = useAppStore()
  const sink = sinkData[nodeId]

  if (!sink) {
    return <div className="vs-sink-empty">{t(language, 'sink.empty')}</div>
  }
  if (sink.kind === 'frame') {
    // La imagen llega como JPEG en base64 por WebSocket.
    return <img className="vs-sink-image" src={`data:image/jpeg;base64,${sink.data}`} alt="sink" />
  }
  if (sink.kind === 'boolean' || sink.kind === 'status') {
    const ok = Boolean(sink.value)
    const text =
      sink.kind === 'status' && sink.value && typeof sink.value === 'object'
        ? String((sink.value as { ok?: boolean }).ok ?? false)
        : String(sink.value)
    const isOk =
      sink.kind === 'status'
        ? Boolean((sink.value as { ok?: boolean } | null)?.ok ?? sink.value)
        : ok
    return (
      <div className={`vs-sink-status ${isOk ? 'is-ok' : 'is-nok'}`}>
        {t(language, isOk ? 'sink.ok' : 'sink.nok')} {sink.kind === 'status' ? '' : `(${text})`}
      </div>
    )
  }
  // Texto, número, coordenadas, rectángulo, detecciones, análisis...
  return <div className="vs-sink-text">{String(JSON.stringify(sink.value ?? ''))}</div>
}

function portTypeText(port: PortSpec, language: Language) {
  // Etiqueta de tipo de un puerto: 1 tipo -> su abreviatura; 2-3 tipos ->
  // unidas con "/"; más de 3 -> "any" (evita cadenas ilegibles como las 8
  // tipos del bloque pause_resume).
  const labels = port.types.map((type) => t(language, `type.${type}`))
  return labels.length > 3 ? t(language, 'type.any') : labels.join('/')
}

function PortHandles({ spec }: { spec: BlockSpec }) {
  const { language } = useAppStore()
  // Puertos de entrada a la izquierda y de salida a la derecha, distribuidos
  // verticalmente (handle id = id del puerto, así las aristas lo identifican).
  // La etiqueta de tipo usa el MISMO `top`% que su handle para quedar alineada.
  const inputTop = (index: number, total: number) => ((index + 0.5) / total) * 100
  return (
    <>
      {spec.inputs.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{ top: `${inputTop(index, spec.inputs.length)}%` }}
        />
      ))}
      {spec.inputs.map((port, index) => (
        <span
          key={`label-${port.id}`}
          className="vs-port-type vs-port-type-in"
          style={{ top: `${inputTop(index, spec.inputs.length)}%` }}
        >
          {portTypeText(port, language)}
        </span>
      ))}
      {spec.outputs.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="source"
          position={Position.Right}
          style={{ top: `${inputTop(index, spec.outputs.length)}%` }}
        />
      ))}
      {spec.outputs.map((port, index) => (
        <span
          key={`label-${port.id}`}
          className="vs-port-type vs-port-type-out"
          style={{ top: `${inputTop(index, spec.outputs.length)}%` }}
        >
          {portTypeText(port, language)}
        </span>
      ))}
    </>
  )
}

export function BlockNode({ id, data, selected }: NodeProps<Node<BlockNodeData>>) {
  const { blocksCatalog, language, flowState, resizeBlock, project } = useAppStore()
  const spec = findBlockSpec(blocksCatalog, data.blockType)
  const category = spec?.category ?? 'processing'
  // Solo se redimensiona con el bloque seleccionado y el flujo detenido.
  const resizable = selected && flowState === 'stopped'
  // Si el bloque tiene tamaño persistido, la caja debe rellenar el nodo; si no,
  // se dimensiona por contenido (comportamiento por defecto).
  const block = project.blocks.find((b) => b.id === id)
  const sized = block?.width != null || block?.height != null

  return (
    <div
      className={`vs-node vs-node-${category} ${selected ? 'is-selected' : ''} ${sized ? 'is-sized' : ''}`}
    >
      {/* Poka-yoke de tamaño: el usuario puede ajustar el bloque dentro de unos
          límites razonables (ni microscópico ni enorme). Se persiste al soltar. */}
      <NodeResizer
        isVisible={resizable}
        minWidth={140}
        minHeight={60}
        maxWidth={420}
        maxHeight={420}
        onResizeEnd={(_event, params) => resizeBlock(id, params.width, params.height)}
      />
      <div className="vs-node-header">{t(language, spec?.name_key ?? data.blockType)}</div>
      <div className="vs-node-body">
        {spec?.category === 'output' && <SinkContent nodeId={id} />}
      </div>
      {spec && <PortHandles spec={spec} />}
    </div>
  )
}