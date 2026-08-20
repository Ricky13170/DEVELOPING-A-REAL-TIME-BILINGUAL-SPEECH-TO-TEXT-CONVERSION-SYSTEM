import { AudioManager } from "./audio.js";
import { SocketManager } from "./socket.js";
import { UIManager } from "./ui.js";
import { generateId } from "./utils.js";

class ASRApp {
  constructor() {
    this.audioMgr = new AudioManager();
    this.socketMgr = new SocketManager();
    this.uiMgr = new UIManager();
    this.isRecording = false;
    this.isConnecting = false;
    this.isFinalizing = false;
    this.stopSaveTimer = null;
    this.serverReady = false;
    this.webRTCAllowed = true;
    this.transcripts = {};
    this.sessionId = null;
    this.lectureTopic = "";
  }

  async init() {
    this.setupAudioCallbacks();
    this.setupSocketCallbacks();
    this.setupUIHandlers();
    this.setupScreenShare();
    this.uiMgr.updateRecordButton(false);
    await this.loadMicrophones();
    await this.checkServerStatus();
  }

  async loadMicrophones() {
    try {
      const mics = await this.audioMgr.getAvailableMicrophones();
      const micList = document.getElementById("micList");
      if (micList && mics.length > 0) {
        micList.innerHTML = mics.slice(0, 3)
          .map(
            (mic) => `
                    <div class="dropdown-item mic-item" data-source="microphone" data-device="${mic.deviceId}">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
                        ${mic.label}
                    </div>
                `,
          )
          .join("");
      }
    } catch (e) {
      console.log("[Mics] Could not enumerate devices");
    }
  }

  async checkServerStatus(attempt = 0) {
    const statusEl = document.getElementById("loadingStatus");
    const hintEl = document.querySelector(".loading-hint");
    const spinnerEl = document.getElementById("loadingSpinner");
    const MAX_ATTEMPTS = 3;

    try {
      if (statusEl) statusEl.textContent = "Connecting to server...";
      if (hintEl)
        hintEl.textContent = "Models are loading, this may take a moment";

      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        this.serverReady = true;
        this.webRTCAllowed = Boolean(data.webrtc_available);
        this.uiMgr.updateTransportStatus("ready");
        this.uiMgr.setCloudExtrasEnabled(
          Array.isArray(data.features) && data.features.includes("groq_extras"),
        );

        if (spinnerEl) spinnerEl.classList.add("hidden");
        if (statusEl) {
          statusEl.textContent = `✓ Ready — ${data.model || "Whisper"}`;
          statusEl.classList.add("ready");
        }
        if (hintEl)
          hintEl.textContent = "Click the record button to start transcribing";

        this.uiMgr.showNotification(`Ready: ${data.model || "Whisper"}`);
      }
    } catch (e) {
      if (attempt < MAX_ATTEMPTS) {
        if (statusEl) statusEl.textContent = "Server is starting up...";
        if (hintEl) hintEl.textContent = "Cold start may take 30-60 seconds";
        setTimeout(() => this.checkServerStatus(attempt + 1), 5000);
      } else {

        if (spinnerEl) spinnerEl.classList.add("hidden");
        if (statusEl) {
          statusEl.textContent = "⚡ Preview Mode";
          statusEl.classList.add("ready");
        }
        if (hintEl)
          hintEl.textContent =
            "No backend detected — run main.py to start the local CPU server.";
        console.log("[ASR] No backend detected, running in preview mode");
        this.uiMgr.updateTransportStatus("offline");
      }
    }
  }

  setupAudioCallbacks() {
    this.audioMgr.onAudioData = (b64) => {
      if (this.isRecording && this.socketMgr.isConnected()) {
        this.socketMgr.send("audio", { audio: b64 });
      }
    };
    this.audioMgr.onLevelUpdate = (rms) => {
      if (this.isRecording) this.uiMgr.updateAudioMeter(rms);
    };
  }

  setupSocketCallbacks() {
    this.socketMgr.onMessage = (data) => {
      if (data.type === "transcript") {
        this.uiMgr.addTranscriptSegment(data);

        if (data.is_final && (data.source || data.target)) {
          const id =
            data.segment_id || Object.keys(this.transcripts).length + 1;
          if (!this.transcripts[id]) this.transcripts[id] = { source: "", target: "" };
          if (data.source) this.transcripts[id].source = data.source;
          if (data.target) this.transcripts[id].target = data.target;
        }
      } else if (data.type === "status") {
        if (data.status === "started") {
          this.uiMgr.showNotification("Recording...");
        } else if (data.status === "stopped") {
          this.uiMgr.showNotification("Stopped");
          this.completeStopSave();
        }
      } else if (data.type === "log") {
        this.uiMgr.showNotification(data.message || "");
      }
    };

    this.socketMgr.onConnected = () => {
      this.isConnecting = false;
      this.serverReady = true;
      this.uiMgr.updateTransportStatus("ws");
    };

    this.socketMgr.onDisconnected = () => {
      this.uiMgr.updateTransportStatus("offline");
      if (this.isRecording) {
        this.uiMgr.showNotification("Disconnected");
        this.stopRecording();
      }
    };

    this.socketMgr.onError = () => {
      this.isConnecting = false;
      this.uiMgr.showNotification("Connection error");
    };
    this.socketMgr.onWebRTCState = (state) => {
      if (state === "connected") this.uiMgr.updateTransportStatus("webrtc");
      if (["failed", "disconnected", "closed"].includes(state)) {
        this.audioMgr.useWebRTC = false;
        if (state !== "closed") this.socketMgr.stopWebRTC();
        console.warn("[ASR] WebRTC unavailable; resumed WebSocket audio fallback");
        if (this.socketMgr.isConnected()) this.uiMgr.updateTransportStatus("ws");
      }
    };
  }

  setupUIHandlers() {
    if (this.uiMgr.el.recordBtn) {
      this.uiMgr.el.recordBtn.onclick = () => {
        if (this.isRecording) this.stopRecording();
        else this.startRecording();
      };
    }

    this.uiMgr.onContextSave = (data) => {
      this.lectureTopic = data.topic || "";
      if (this.socketMgr.isConnected()) {
        this.socketMgr.send("context", data);
        this.uiMgr.showNotification("Context saved");
      }
    };

    // Mid-session language change
    this.uiMgr.onLangChange = (langs) => {
      if (this.isRecording && this.socketMgr.isConnected()) {
        this.socketMgr.send("lang_change", {
          srcLang: langs.srcWhisper,
          srcTranslation: langs.srcTranslation,
          tgtTranslation: langs.tgtTranslation,
        });
        this.uiMgr.showNotification("Language switching...");
      }
    };

    // Microphone selection from dropdown
    const audioDropdown = document.getElementById("audioDropdown");
    if (audioDropdown) {
      audioDropdown.addEventListener("click", (e) => {
        const item = e.target.closest("[data-source]");
        if (!item) return;

        const source = item.dataset.source;
        const deviceId = item.dataset.device;

        if (source === "microphone" && deviceId) {
          this.audioMgr.setMicrophone(deviceId);
          this.uiMgr.setAudioSource("microphone");
          // Update checkmarks — only mic items
          audioDropdown.querySelectorAll('.mic-item').forEach(el => {
            el.classList.toggle('selected', el.dataset.device === deviceId);
          });
        } else if (source === "computer") {
          this.uiMgr.setAudioSource("computer");
        } else if (source === "mixed") {
          this.uiMgr.setAudioSource("mixed");
        }

        audioDropdown.classList.remove("active");
      });
    }
  }

  setupScreenShare() {
    // Screen share button toggle
    this.uiMgr.onScreenShareToggle = () => {
      if (this.audioMgr.isScreenSharing) {
        this.audioMgr.stopScreenShare();
      } else {
        this._startScreenShare();
      }
    };

    // Audio manager callbacks for screen share
    this.audioMgr.onScreenStream = (stream) => {
      const currentSource = this.uiMgr.getAudioSource();
      this.uiMgr.showScreenPanel(stream);
      if (currentSource !== "computer" && currentSource !== "mixed") {
        this.uiMgr.setAudioSource("screen");
      }
    };

    this.audioMgr.onScreenStop = () => {
      const currentSource = this.uiMgr.getAudioSource();
      this.uiMgr.hideScreenPanel();
      if (currentSource === "screen") {
        this.uiMgr.setAudioSource("microphone");
      }
    };
  }

  async _startScreenShare() {
    try {
      const currentSource = this.uiMgr.getAudioSource();
      await this.audioMgr.startScreenShare({ withAudio: currentSource !== "computer" && currentSource !== "mixed" });
    } catch (err) {
      console.error("[ScreenShare] Error:", err);
      this.uiMgr.showNotification(err.message || "Could not share screen");
    }
  }

  async startRecording() {
    if (this.isConnecting) return;
    if (this.isFinalizing) {
      this.uiMgr.showNotification("Finalizing the previous translation...");
      return;
    }
    if (!this.serverReady) {
      this.uiMgr.showNotification("Server loading...");
      // Show loading spinner on record button
      const recordBtn = this.uiMgr.el.recordBtn;
      const spinner = document.getElementById('recordLoadingSpinner');
      if (recordBtn) recordBtn.classList.add('loading');
      if (spinner) spinner.classList.remove('hidden');
      await this.checkServerStatus();
      if (recordBtn) recordBtn.classList.remove('loading');
      if (spinner) spinner.classList.add('hidden');
      if (!this.serverReady) return;
    }

    this.isConnecting = true;
    this.uiMgr.showNotification("Connecting...");

    try {
      if (!this.socketMgr.isConnected()) {
        await this.socketMgr.connect();
      }

      // Determine audio source
      let source = this.uiMgr.getAudioSource();
      if (this.audioMgr.isScreenSharing && source !== "computer" && source !== "mixed") {
        source = "screen";
      }
      await this.audioMgr.startRecording(source);

      this.uiMgr.clearTranscripts();
      this.transcripts = {};
      this.sessionId = generateId();

      const topic = this.lectureTopic || this.uiMgr.getLectureTopic() || "";
      const langs = this.uiMgr.getSelectedLanguages();

      this.socketMgr.send("start", {
        srcLang: langs.srcWhisper,
        tgtLang: langs.tgtCode,
        srcTranslation: langs.srcTranslation,
        tgtTranslation: langs.tgtTranslation,
        translate: true,
        topic: topic,
      });

      // WebSocket audio covers the entire WebRTC negotiation window so the
      // first words are never discarded while waiting for ICE.
      this.isRecording = true;
      this.uiMgr.startTimer();
      this.uiMgr.updateRecordButton(true);

      // Try WebRTC for lower latency audio transport
      const stream = this.audioMgr.getActiveStream();
      if (stream && this.webRTCAllowed) {
        const webrtcOk = await this.socketMgr.startWebRTC(stream);
        if (webrtcOk) {
          this.audioMgr.useWebRTC = true;
          this.uiMgr.updateTransportStatus("webrtc");
          console.log('[ASR] Using WebRTC audio transport');
        } else {
          this.audioMgr.useWebRTC = false;
          this.uiMgr.updateTransportStatus("ws");
          console.log('[ASR] Using WebSocket audio transport (fallback)');
        }
      } else {
        this.audioMgr.useWebRTC = false;
        this.uiMgr.updateTransportStatus("ws");
      }

      this.isConnecting = false;
    } catch (err) {
      this.isConnecting = false;
      this.isRecording = false;
      if (this.audioMgr.isRecording) this.audioMgr.stopRecording();
      this.socketMgr.stopWebRTC();
      this.uiMgr.updateRecordButton(false);
      this.uiMgr.resetAudioMeter();
      this.uiMgr.showNotification(err.message || "Could not start");
    }
  }

  async stopRecording() {
    const waitForServer = this.socketMgr.isConnected();
    this.isFinalizing = true;
    const wasWebRTC = this.audioMgr.useWebRTC;
    this.audioMgr.useWebRTC = false;
    this.audioMgr.stopRecording();
    this.socketMgr.stopWebRTC();

    // Let the last RTP packet reach the server. WebSocket flushes synchronously
    // above, so ordering is also correct for the fallback transport.
    if (wasWebRTC) await new Promise((resolve) => setTimeout(resolve, 120));
    if (waitForServer && this.socketMgr.isConnected()) this.socketMgr.send("stop");

    this.isRecording = false;
    this.isConnecting = false;
    this.uiMgr.stopTimer();
    this.uiMgr.resetAudioMeter();
    this.uiMgr.updateRecordButton(false);

    if (!waitForServer) {
      this.completeStopSave();
      return;
    }

    clearTimeout(this.stopSaveTimer);
    this.stopSaveTimer = setTimeout(() => this.completeStopSave(), 12000);
  }

  completeStopSave() {
    if (!this.isFinalizing) return;
    clearTimeout(this.stopSaveTimer);
    this.stopSaveTimer = null;
    this.isFinalizing = false;
    this.saveRecording();
  }

  saveRecording() {
    const segments = Object.values(this.transcripts).filter(
      (t) => t.source || t.target,
    );
    if (segments.length === 0) return;

    try {
      const recordings = JSON.parse(localStorage.getItem("recordings") || "[]");
      const now = new Date();

      const langs = this.uiMgr.getSelectedLanguages();
      const rec = {
        id: this.sessionId,
        date: now.toLocaleDateString("en-CA").replace(/-/g, "."),
        time: now.toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        duration: this.uiMgr.el.timer?.textContent || "00:00",
        sourceLang: langs.srcCode,
        targetLang: langs.tgtCode,
        transcript: segments.map((t) => ({
          source: t.source || "",
          target: t.target || "",
        })),
      };

      recordings.unshift(rec);
      if (recordings.length > 50) recordings.pop();

      localStorage.setItem("recordings", JSON.stringify(recordings));
      this.uiMgr.showNotification(`Saved ${segments.length} segments`);
      this.uiMgr.loadRecordingsSidebar();
    } catch (e) {
      console.error("[Save] Error:", e);
    }
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const app = new ASRApp();
  app.init();
});
