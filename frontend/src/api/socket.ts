// Cliente WebSocket de tiempo real.
// Recibe frames (JPEG base64), valores de sinks, estado y errores del backend.
// Reconexión automática con reintento y limpieza al cerrar.
import type { WsMessage } from '../types'

const RECONNECT_DELAY_MS = 1000

export class SocketClient {
  private ws: WebSocket | null = null
  private shouldReconnect = true
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(
    private readonly url: string,
    private readonly onMessage: (message: WsMessage) => void,
    private readonly onOpen: () => void,
    private readonly onClose: () => void,
  ) {}

  connect(): void {
    this.shouldReconnect = true
    this.open()
  }

  private open(): void {
    // La URL del WS se deriva de la ventana (mismo origen en producción;
    // Vite reenvía /ws en desarrollo).
    const url = this.url || `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.onOpen()
    }

    ws.onmessage = (event) => {
      try {
        this.onMessage(JSON.parse(event.data) as WsMessage)
      } catch {
        // Mensaje corrupto: se ignora (no debe tumbar la conexión).
      }
    }

    ws.onclose = () => {
      this.onClose()
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => this.open(), RECONNECT_DELAY_MS)
      }
    }

    ws.onerror = () => {
      // El error se gestiona en onclose; aquí solo se evita ruido.
      ws.close()
    }
  }

  sendCommand(command: string, extra?: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ command, ...extra }))
    }
  }

  close(): void {
    this.shouldReconnect = false
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }
}