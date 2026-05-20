/**
 * ComfyUI WebSocket integration for real-time generation progress tracking.
 *
 * Connects to ComfyUI's WebSocket endpoint to receive execution events:
 * - execution_start: Generation has started
 * - execution_cached: Using cached outputs (progress info)
 * - progress: Step progress (current/total steps)
 * - executing: A specific node is executing (null = done)
 * - execution_error: An error occurred
 * - execution_interrupted: Generation was interrupted
 *
 * Usage:
 *   const ws = new ComfyUIWebSocket('ws://127.0.0.1:8188', clientId)
 *   ws.onStatusChange = (status) => { ... }
 *   ws.onProgress = (step, maxStep) => { ... }
 *   ws.onComplete = (promptId) => { ... }
 *   ws.onError = (errorMessage) => { ... }
 *   await ws.connect()
 *   // ... submit prompt with client_id ...
 *   // events will fire as generation progresses
 *   ws.disconnect()
 */

const API_BASE = "/api";

export class ComfyUIWebSocket {
  /**
   * @param {string} serverUrl - HTTP URL of the ComfyUI server (e.g. http://127.0.0.1:8188)
   * @param {string} clientId - Unique client ID for the WebSocket connection
   */
  constructor(serverUrl, clientId) {
    this.serverUrl = serverUrl;
    this.clientId = clientId;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
    this.reconnectDelay = 1000;
    this.connected = false;

    // Event callbacks
    this.onStatusChange = null; // (status: 'connecting'|'connected'|'disconnected'|'error') => void
    this.onProgress = null;     // (step: number, maxStep: number) => void
    this.onComplete = null;     // (promptId: string) => void
    this.onError = null;        // (errorMessage: string) => void
    this.onNodeExecuting = null; // (nodeId: string|null, promptId: string) => void
  }

  /**
   * Convert an HTTP URL to a WebSocket URL.
   */
  _httpToWs(url) {
    return url
      .replace(/^http:/, "ws:")
      .replace(/^https:/, "wss:")
      .replace(/\/+$/, "");
  }

  /**
   * Connect to the ComfyUI WebSocket.
   * @returns {Promise<void>} Resolves when connected, rejects on failure.
   */
  connect() {
    return new Promise((resolve, reject) => {
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
        resolve();
        return;
      }

      const wsUrl = `${this._httpToWs(this.serverUrl)}/ws?clientId=${this.clientId}`;
      this._notifyStatus("connecting");

      try {
        this.ws = new WebSocket(wsUrl);
      } catch (err) {
        this._notifyStatus("error");
        reject(new Error(`Failed to create WebSocket: ${err.message}`));
        return;
      }

      this.ws.onopen = () => {
        this.connected = true;
        this.reconnectAttempts = 0;
        this._notifyStatus("connected");
        resolve();
      };

      this.ws.onerror = (event) => {
        this.connected = false;
        this._notifyStatus("error");
        // Only reject the connect() promise on the first attempt
        // (not during reconnection attempts)
        if (this.reconnectAttempts === 0) {
          reject(new Error("WebSocket connection error"));
        }
      };

      this.ws.onclose = (event) => {
        this.connected = false;
        this._notifyStatus("disconnected");

        // Auto-reconnect on unexpected close (not manual disconnect)
        if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts);
        }
      };

      this.ws.onmessage = (event) => {
        this._handleMessage(event);
      };
    });
  }

  /**
   * Disconnect from the WebSocket.
   */
  disconnect() {
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect
    if (this.ws) {
      this.ws.close(1000, "Manual disconnect");
      this.ws = null;
    }
    this.connected = false;
    this._notifyStatus("disconnected");
  }

  /**
   * Handle incoming WebSocket messages from ComfyUI.
   */
  _handleMessage(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      // Binary data or non-JSON — ignore
      return;
    }

    const msgType = data.type;
    const msgData = data.data || {};

    switch (msgType) {
      case "status":
        // Queue status update — not critical for our use case
        break;

      case "execution_start":
        // Generation has started for a prompt
        if (this.onNodeExecuting) {
          this.onNodeExecuting(null, msgData.prompt_id);
        }
        break;

      case "execution_cached":
        // Some nodes were cached — generation is progressing
        break;

      case "progress":
        // Step progress update
        if (this.onProgress) {
          this.onProgress(msgData.value || 0, msgData.max || 0);
        }
        break;

      case "executing":
        // A node is executing. node=null means execution is complete.
        if (msgData.node === null) {
          // Generation complete!
          if (this.onComplete) {
            this.onComplete(msgData.prompt_id);
          }
        } else {
          if (this.onNodeExecuting) {
            this.onNodeExecuting(msgData.node, msgData.prompt_id);
          }
        }
        break;

      case "execution_error":
        // An error occurred during generation
        if (this.onError) {
          const errMsg = msgData.exception_message || msgData.message || "Unknown execution error";
          this.onError(errMsg);
        }
        break;

      case "execution_interrupted":
        // Generation was interrupted
        if (this.onError) {
          this.onError("Generation was interrupted");
        }
        break;

      default:
        // Unknown message type — ignore
        break;
    }
  }

  /**
   * Notify status change callback.
   */
  _notifyStatus(status) {
    if (this.onStatusChange) {
      this.onStatusChange(status);
    }
  }
}

/**
 * Fetch a unique client ID from the backend for WebSocket connections.
 * @returns {Promise<string>} A unique client ID
 */
export async function fetchClientId() {
  const res = await fetch(`${API_BASE}/comfyui/client-id`);
  if (!res.ok) {
    // Fallback to a local UUID if the server is unavailable
    return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
  const data = await res.json();
  return data.client_id;
}

/**
 * Fetch generation history details from ComfyUI (including output images).
 * @param {string} promptId - The prompt ID to look up
 * @param {string} serverUrl - ComfyUI server URL
 * @returns {Promise<object>} History detail with status and outputs
 */
export async function fetchComfyUIHistory(promptId, serverUrl) {
  const params = new URLSearchParams({ server_url: serverUrl });
  const res = await fetch(
    `${API_BASE}/comfyui/history/${encodeURIComponent(promptId)}?${params.toString()}`
  );
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `History fetch failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Build a URL for proxying a ComfyUI image through the backend.
 * @param {object} imageInfo - Image info from history (filename, subfolder, type)
 * @param {string} serverUrl - ComfyUI server URL
 * @returns {string} URL to fetch the image through the backend proxy
 */
export function buildComfyUIImageUrl(imageInfo, serverUrl) {
  const params = new URLSearchParams({
    server_url: serverUrl,
    filename: imageInfo.filename,
    subfolder: imageInfo.subfolder || "",
    type: imageInfo.type || "output",
  });
  return `${API_BASE}/comfyui/image?${params.toString()}`;
}