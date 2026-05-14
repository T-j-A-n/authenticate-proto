/**
 * Gaze Tracking Module
 * Monitors student eye movements during coding test
 * Uses webgazer.js for browser-based eye tracking
 */

export class GazeTracker {
  constructor(sessionId, onGazeData, onGazeAlert) {
    this.sessionId = sessionId;
    this.onGazeData = onGazeData;
    this.onGazeAlert = onGazeAlert;
    this.isTracking = false;
    this.gazeData = [];
    this.offScreenTime = 0;
    this.lastGazeTime = null;
    this.calibrated = false;
    this.offScreenThreshold = 5000; // 5 seconds threshold
    this.trackedRegions = {
      editor: null,
      screen: null,
    };
  }

  /**
   * Initialize WebGazer and start tracking
   */
  async initialize() {
    try {
      // Load webgazer library
      const script = document.createElement("script");
      script.src = "https://webgazer.cs.brown.edu/webgazer.js";
      script.async = true;

      script.onload = () => {
        this._setupWebGazer();
      };

      script.onerror = () => {
        console.warn("WebGazer failed to load - gaze tracking disabled");
      };

      document.head.appendChild(script);
    } catch (e) {
      console.error("Failed to initialize gaze tracker:", e);
    }
  }

  _setupWebGazer() {
    if (!window.webgazer) {
      console.warn("WebGazer not available");
      return;
    }

    // Request camera permissions and start tracking
    window.webgazer
      .setRegression("ridge")
      .begin()
      .then(() => {
        this.isTracking = true;
        this.calibrated = true;
        console.log("✓ Gaze tracking initialized");

        // Start monitoring gaze
        this._startGazeMonitoring();
      })
      .catch((err) => {
        console.warn("Could not start gaze tracking:", err);
        this.isTracking = false;
      });
  }

  _startGazeMonitoring() {
    if (!window.webgazer) return;

    // Get gaze data continuously
    window.webgazer.setGazeListener((data, elapsedTime) => {
      if (data == null) return;

      const { x, y } = data;

      // Record gaze point
      this.lastGazeTime = Date.now();
      this.gazeData.push({
        timestamp: Date.now(),
        x,
        y,
        onScreen: this._isGazeOnEditor(x, y),
      });

      // Keep only last 100 data points
      if (this.gazeData.length > 100) {
        this.gazeData.shift();
      }

      // Callback with current data
      if (this.onGazeData) {
        this.onGazeData({
          x,
          y,
          onScreen: this._isGazeOnEditor(x, y),
          timestamp: Date.now(),
        });
      }
    });

    // Monitor for off-screen gaze
    this._checkOffScreenGaze();
  }

  _isGazeOnEditor(x, y) {
    // Check if gaze is within editor area
    const editor = document.querySelector('[role="textbox"]');
    if (!editor) return false;

    const rect = editor.getBoundingClientRect();
    return (
      x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
    );
  }

  _checkOffScreenGaze() {
    setInterval(() => {
      if (!this.isTracking || this.gazeData.length === 0) return;

      const now = Date.now();
      const lastGaze = this.gazeData[this.gazeData.length - 1];

      // Check if gaze is off-screen
      if (!lastGaze.onScreen) {
        this.offScreenTime += 1000; // Add 1 second

        // Alert if exceeded threshold
        if (
          this.offScreenTime > this.offScreenThreshold &&
          this.offScreenTime % 2000 === 0
        ) {
          this._logGazeAlert("off-screen", {
            duration: this.offScreenTime,
            x: lastGaze.x,
            y: lastGaze.y,
          });
        }
      } else {
        // Reset counter when eyes back on screen
        if (this.offScreenTime > 0) {
          this._logGazeAlert("on-screen-return", {
            duration: this.offScreenTime,
          });
          this.offScreenTime = 0;
        }
      }
    }, 1000);
  }

  _logGazeAlert(alertType, data) {
    if (this.onGazeAlert) {
      this.onGazeAlert({
        type: alertType,
        timestamp: Date.now(),
        ...data,
      });
    }

    // Send to backend
    this._sendGazeEvent(alertType, data);
  }

  async _sendGazeEvent(eventType, data) {
    try {
      await fetch("http://localhost:8000/api/gaze-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: this.sessionId,
          event_type: eventType,
          event_data: data,
          timestamp: new Date().toISOString(),
        }),
      });
    } catch (e) {
      console.error("Failed to send gaze event:", e);
    }
  }

  /**
   * Calibrate gaze tracker
   * Call this after user sees calibration points
   */
  calibrate() {
    if (!window.webgazer) return;

    console.log("Starting gaze calibration...");
    window.webgazer.showVideo(true);

    // Show calibration UI (simplified)
    alert("Look at the center of the screen and press OK when ready");

    this.calibrated = true;
    console.log("✓ Gaze calibration complete");
  }

  /**
   * Get gaze statistics for current session
   */
  getStats() {
    if (this.gazeData.length === 0) {
      return {
        totalSamples: 0,
        onScreenPercentage: 0,
        offScreenTime: this.offScreenTime,
      };
    }

    const onScreen = this.gazeData.filter((d) => d.onScreen).length;
    const percentage = (onScreen / this.gazeData.length) * 100;

    return {
      totalSamples: this.gazeData.length,
      onScreenPercentage: percentage,
      offScreenTime: this.offScreenTime,
      lastGazeTime: this.lastGazeTime,
    };
  }

  /**
   * Stop gaze tracking
   */
  stop() {
    if (window.webgazer) {
      window.webgazer.end();
    }
    this.isTracking = false;
    console.log("Gaze tracking stopped");
  }
}
