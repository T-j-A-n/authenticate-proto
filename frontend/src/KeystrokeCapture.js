export class KeystrokeCapture {
  constructor(sessionId, onScore) {
    this.sessionId = sessionId
    this.onScore = onScore
    this.buffer = []
    this.pendingKeys = {}
    this.lastKeyDownTime = null
    this.lastKeyUpTime = null
    this._onKeyDown = this._onKeyDown.bind(this)
    this._onKeyUp = this._onKeyUp.bind(this)
  }

  attach(element) {
    this.element = element
    element.addEventListener('keydown', this._onKeyDown, true)
    element.addEventListener('keyup', this._onKeyUp, true)
  }

  detach() {
    if (this.element) {
      this.element.removeEventListener('keydown', this._onKeyDown, true)
      this.element.removeEventListener('keyup', this._onKeyUp, true)
    }
  }

  _onKeyDown(e) {
    const now = performance.now()
    this.pendingKeys[e.keyCode] = now
    this.lastKeyDownTime = now
  }

  _onKeyUp(e) {
    const upTime = performance.now()
    const downTime = this.pendingKeys[e.keyCode]
    if (downTime == null) return

    delete this.pendingKeys[e.keyCode]

    const hold_time_ms = upTime - downTime
    const iki_kd_ms = this.lastKeyDownTime != null ? downTime - this.lastKeyDownTime : 0
    const iki_ku_ms = this.lastKeyUpTime != null ? downTime - this.lastKeyUpTime : 0

    this.lastKeyUpTime = upTime

    this.buffer.push([hold_time_ms, iki_kd_ms, iki_ku_ms, e.keyCode])

    if (this.buffer.length % 10 === 0 && this.buffer.length >= 50) {
      const window = this.buffer.slice(-50)
      this._sendWindow(window)
    }
  }

  async _sendWindow(windowData) {
    try {
      const res = await fetch('http://localhost:8000/api/keystroke-window', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: this.sessionId, window_data: windowData }),
      })
      const data = await res.json()
      if (this.onScore) this.onScore(data.similarity_score)
    } catch (_) {}
  }
}
