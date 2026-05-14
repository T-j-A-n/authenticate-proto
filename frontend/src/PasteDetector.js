/**
 * Paste Detection Module
 * Monitors for paste events in the code editor
 * Flags suspicious paste activity
 */

export class PasteDetector {
  constructor(sessionId, onPasteDetected) {
    this.sessionId = sessionId;
    this.onPasteDetected = onPasteDetected;
    this.pasteHistory = [];
    this.isListening = false;
  }

  /**
   * Attach paste detection to editor element
   */
  attach(editorElement) {
    if (!editorElement) return;

    this.editorElement = editorElement;

    // Listen for paste events
    editorElement.addEventListener("paste", (e) => this._handlePaste(e));

    // Also listen on window for global paste
    document.addEventListener("paste", (e) => this._handlePaste(e));

    // Listen for keyboard shortcut Ctrl+V / Cmd+V
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "v") {
        this._flagPasteAttempt("keyboard-shortcut");
      }
    });

    // Listen for right-click paste
    editorElement.addEventListener("contextmenu", (e) => {
      // Check if paste option was shown
      setTimeout(() => {
        this._flagPasteAttempt("context-menu");
      }, 100);
    });

    this.isListening = true;
    console.log("✓ Paste detection attached");
  }

  /**
   * Handle paste events
   */
  _handlePaste(e) {
    const clipboardData = e.clipboardData || window.clipboardData;
    const pastedText = clipboardData.getData("text");

    if (!pastedText) return;

    // Don't flag very short pastes (like single characters)
    if (pastedText.length < 3) return;

    const pasteEvent = {
      timestamp: Date.now(),
      length: pastedText.length,
      content: pastedText.substring(0, 100), // Store first 100 chars
      contentHash: this._hashString(pastedText),
      source: this._detectPasteSource(),
    };

    this.pasteHistory.push(pasteEvent);

    // Send alert
    this._logPasteAlert(pasteEvent);
  }

  /**
   * Detect paste attempt even if content is empty
   */
  _flagPasteAttempt(source) {
    const event = {
      timestamp: Date.now(),
      type: "paste-attempt",
      source,
      content: "N/A",
      flagged: true,
    };

    this._logPasteAlert(event);
  }

  /**
   * Detect paste source (keyboard, context menu, etc)
   */
  _detectPasteSource() {
    // This is a simplified detection
    // In real scenario, you'd track which method was used
    return "unknown";
  }

  /**
   * Simple string hash for duplicate detection
   */
  _hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash; // Convert to 32bit integer
    }
    return hash.toString(16);
  }

  /**
   * Log paste event and send to backend
   */
  _logPasteAlert(pasteEvent) {
    console.warn("⚠️ Paste detected:", pasteEvent);

    if (this.onPasteDetected) {
      this.onPasteDetected(pasteEvent);
    }

    // Send to backend
    this._sendPasteEvent(pasteEvent);
  }

  async _sendPasteEvent(pasteEvent) {
    try {
      await fetch("http://localhost:8000/api/paste-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: this.sessionId,
          paste_length: pasteEvent.length,
          paste_content_preview: pasteEvent.content,
          paste_source: pasteEvent.source,
          timestamp: new Date().toISOString(),
        }),
      });
    } catch (e) {
      console.error("Failed to send paste event:", e);
    }
  }

  /**
   * Get paste statistics
   */
  getStats() {
    return {
      totalPastes: this.pasteHistory.length,
      totalCharactersPasted: this.pasteHistory.reduce(
        (sum, p) => sum + (p.length || 0),
        0,
      ),
      averagePasteSize:
        this.pasteHistory.length > 0
          ? Math.round(
              this.pasteHistory.reduce((sum, p) => sum + (p.length || 0), 0) /
                this.pasteHistory.length,
            )
          : 0,
      pasteEvents: this.pasteHistory,
    };
  }

  /**
   * Detach paste detection
   */
  detach() {
    if (this.editorElement) {
      this.editorElement.removeEventListener("paste", (e) =>
        this._handlePaste(e),
      );
    }
    this.isListening = false;
    console.log("Paste detection detached");
  }
}
