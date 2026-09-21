// Lienzo central: editor de grafos con React Flow.
// Convierte el proyecto (fuente de verdad del store) en nodos y aristas,
// aplica los cambios de vuelta y valida las conexiones antes de aceptarlas.
import { useCallback } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type Node as RfNode,
  type Edge as RfEdge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { useAppStore } from '../store/appStore'
import { connectionKey, validateConnection } from '../utils/graph'
import { BlockNode, type BlockNodeData } from './BlockNode'

const nodeTypes = { block: BlockNode }

function FlowCanvasInner() {
  const { project, flowState, moveBlock, removeBlock, addConnection, removeConnection, addError, setSelectedNodeId, selectedNodeId, setSelectedEdgeId, selectedEdgeId } = useAppStore()

  const editable = flowState === 'stopped'
  const { screenToFlowPosition } = useReactFlow()

  // Proyecto -> nodos/aristas de React Flow (derivado, se recalcula al cambiar).
  // La selección es controlada desde el store para que el panel siempre refleje
  // el nodo seleccionado (evita el desfase al reconstruir los nodos) y para que
  // las aristas seleccionadas se puedan borrar con Supr/Retroceso.
  const nodes: RfNode<BlockNodeData>[] = project.blocks.map((block) => ({
    id: block.id,
    type: 'block',
    position: { x: block.x, y: block.y },
    data: { blockType: block.type },
    selected: selectedNodeId === block.id,
    // Tamaño persistido (null/undefined = automático).
    width: block.width ?? undefined,
    height: block.height ?? undefined,
  }))
  const edges: RfEdge[] = project.connections.map((connection) => {
    const id = connectionKey(connection)
    return {
      id,
      source: connection.from.block,
      sourceHandle: connection.from.port,
      target: connection.to.block,
      targetHandle: connection.to.port,
      selected: selectedEdgeId === id,
    }
  })

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const change of changes) {
        if (change.type === 'position' && change.dragging === false && change.position) {
          moveBlock(change.id, change.position.x, change.position.y)
        } else if (change.type === 'remove') {
          removeBlock(change.id)
        }
      }
    },
    [moveBlock, removeBlock],
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes) {
        // El id de cada arista codifica la conexión (from:port->to:port).
        if (change.type === 'remove') {
          const [from, to] = change.id.split('->')
          const [fromBlock, fromPort] = from.split(':')
          const [toBlock, toPort] = to.split(':')
          removeConnection(fromBlock, fromPort, toBlock, toPort)
        } else if (change.type === 'select' && change.selected) {
          // La selección se controla desde el store: al hacer clic en una
          // arista queda seleccionada y Supr/Retroceso la elimina. Los cambios
          // de deselección se ignoran (los limpia onPaneClick/onNodeClick) para
          // evitar que un orden desfavorable apague la selección recién hecha.
          setSelectedEdgeId(change.id)
        }
      }
    },
    [removeConnection, setSelectedEdgeId],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return
      const result = addConnection(
        connection.source,
        connection.sourceHandle ?? 'out',
        connection.target,
        connection.targetHandle ?? 'in',
      )
      if (!result.ok && result.error) {
        addError(result.error.code, result.error.params)
      }
    },
    [addConnection, addError],
  )

  const isValidConnection = useCallback(
    (connection: RfEdge | Connection) => {
      if (!connection.source || !connection.target) return false
      // Reutiliza la misma validación que al conectar (tipos, entrada única,
      // sin auto-conexión, sin ciclos). Solo permite arrastrar si es válida.
      const error = validateConnection(
        useAppStore.getState().blocksCatalog,
        useAppStore.getState().project,
        connection.source,
        connection.sourceHandle ?? 'out',
        connection.target,
        connection.targetHandle ?? 'in',
      )
      return error === null
    },
    [],
  )

  // La selección se controla desde el store: clic en nodo selecciona el bloque
  // y clic en el lienzo vacío limpia la selección del panel.
  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: RfNode) => {
      setSelectedNodeId(node.id)
      // Un nodo y una arista no se seleccionan a la vez.
      setSelectedEdgeId(null)
    },
    [setSelectedNodeId, setSelectedEdgeId],
  )

  const onEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: RfEdge) => {
      setSelectedEdgeId(edge.id)
      setSelectedNodeId(null)
    },
    [setSelectedEdgeId, setSelectedNodeId],
  )

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
    setSelectedEdgeId(null)
  }, [setSelectedNodeId, setSelectedEdgeId])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      if (!editable) return
      const type = event.dataTransfer.getData('application/vs-block')
      if (!type) return
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      const { addBlock } = useAppStore.getState()
      addBlock(type, position.x, position.y)
    },
    [editable, screenToFlowPosition],
  )

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
  }, [])

  return (
    <div className="vs-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        onDrop={onDrop}
        onDragOver={onDragOver}
        nodesDraggable={editable}
        nodesConnectable={editable}
        deleteKeyCode={editable ? ['Backspace', 'Delete'] : null}
        fitView
        proOptions={{ hideAttribution: false }}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  )
}

export function FlowCanvas() {
  // El provider es necesario para screenToFlowPosition (dropeo de bloques).
  return (
    <ReactFlowProvider>
      <FlowCanvasInner />
    </ReactFlowProvider>
  )
}