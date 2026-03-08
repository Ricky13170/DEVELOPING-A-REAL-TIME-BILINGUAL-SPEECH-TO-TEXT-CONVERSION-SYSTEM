import { AudioManager } from "./audio.js";
import { SocketManager } from "./socket.js";
import { UIManager } from "./ui.js";
import { SubtitleOverlay } from "./subtitle.js";
import { generateId } from "./utils.js";

class ASRApp {
  constructor() {
    this.audioMgr = new AudioManager();
    this.socketMgr = new SocketManager();
    this.uiMgr = new UIManager();
    this.subtitleOverlay = null;
    this.isRecording = false;
    this.isConnecting = false;
    this.serverReady = false;
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
        // No backend — switch to design preview mode
        if (spinnerEl) spinnerEl.classList.add("hidden");
        if (statusEl) {
          statusEl.textContent = "⚡ Preview Mode";
          statusEl.classList.add("ready");
        }
        if (hintEl)
          hintEl.textContent =
            "No backend detected — UI preview only. Deploy to Modal for full ASR.";
        console.log("[ASR] No backend detected, running in preview mode");
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

        // Update subtitles on screen share
        if (this.subtitleOverlay) {
          this.subtitleOverlay.update(
            data.source || "",
            data.target || "",
            data.is_final,
          );
        }

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
        }
      } else if (data.type === "log") {
        this.uiMgr.showNotification(data.message || "");
      }
    };

    this.socketMgr.onConnected = () => {
      this.isConnecting = false;
      this.serverReady = true;
    };

    this.socketMgr.onDisconnected = () => {
      if (this.isRecording) {
        this.uiMgr.showNotification("Disconnected");
        this.stopRecording();
      }
    };

    this.socketMgr.onError = () => {
      this.isConnecting = false;
      this.uiMgr.showNotification("Connection error");
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
          srcNllb: langs.srcNllb,
          tgtNllb: langs.tgtNllb,
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
          const label = item.textContent.trim();
          document.getElementById("audioSourceText").textContent =
            label.substring(0, 15);
        } else if (source === "computer") {
          this.uiMgr.setAudioSource("computer");
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
      this.uiMgr.showScreenPanel(stream);

      // Create subtitle overlay
      const videoWrap = document.getElementById("screenVideoWrap");
      if (videoWrap && !this.subtitleOverlay) {
        this.subtitleOverlay = new SubtitleOverlay(videoWrap);
      }

      this.uiMgr.setAudioSource("screen");
    };

    this.audioMgr.onScreenStop = () => {
      this.uiMgr.hideScreenPanel();

      if (this.subtitleOverlay) {
        this.subtitleOverlay.destroy();
        this.subtitleOverlay = null;
      }

      this.uiMgr.setAudioSource("microphone");
    };
  }

  async _startScreenShare() {
    try {
      await this.audioMgr.startScreenShare();
    } catch (err) {
      console.error("[ScreenShare] Error:", err);
      this.uiMgr.showNotification(err.message || "Could not share screen");
    }
  }

  async startRecording() {
    if (this.isConnecting) return;
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
      if (this.audioMgr.isScreenSharing) {
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
        srcNllb: langs.srcNllb,
        tgtNllb: langs.tgtNllb,
        translate: true,
        topic: topic,
      });

      this.isRecording = true;
      this.isConnecting = false;
      this.uiMgr.startTimer();
      this.uiMgr.updateRecordButton(true);
    } catch (err) {
      this.isConnecting = false;
      this.isRecording = false;
      this.uiMgr.updateRecordButton(false);
      this.uiMgr.resetAudioMeter();
      this.uiMgr.showNotification(err.message || "Could not start");
    }
  }

  async stopRecording() {
    if (this.socketMgr.isConnected()) {
      this.socketMgr.send("stop");
    }

    this.audioMgr.stopRecording();

    this.isRecording = false;
    this.isConnecting = false;
    this.uiMgr.stopTimer();
    this.uiMgr.resetAudioMeter();
    this.uiMgr.updateRecordButton(false);

    await new Promise((r) => setTimeout(r, 1500));
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

      const rec = {
        id: this.sessionId,
        date: now.toLocaleDateString("en-CA").replace(/-/g, "."),
        time: now.toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        duration: this.uiMgr.el.timer?.textContent || "00:00",
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
