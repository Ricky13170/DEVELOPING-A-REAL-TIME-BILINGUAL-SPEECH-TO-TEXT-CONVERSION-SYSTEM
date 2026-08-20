"""
WebRTC audio transport layer.

Uses aiortc to receive audio via WebRTC, providing lower latency
than base64-over-WebSocket. Falls back to WebSocket if WebRTC is
unavailable.

Signaling is done over the existing WebSocket connection:
  Client→Server: {"type": "webrtc_offer", "sdp": "..."}
  Server→Client: {"type": "webrtc_answer", "sdp": "..."}
  Client→Server: {"type": "webrtc_ice", "candidate": {...}}
  Server→Client: {"type": "webrtc_ice", "candidate": {...}}
"""

import asyncio
import numpy as np
import logging
from typing import Optional, Callable, Awaitable

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.sdp import candidate_from_sdp
    from av import AudioFrame
    from av.audio.resampler import AudioResampler
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False
    print("[WebRTC] aiortc not installed — WebRTC disabled, using WebSocket fallback")

from backend.config import SAMPLE_RATE

logger = logging.getLogger(__name__)


class WebRTCTransport:
    """
    Manages a WebRTC peer connection for receiving audio.

    Audio frames received via WebRTC are resampled to 16kHz mono
    and delivered to the session's audio handler via callback.
    """

    def __init__(self, on_audio: Callable[[np.ndarray], Awaitable[None]]):
        """
        Args:
            on_audio: Async callback receiving float32 audio chunks (16kHz mono)
        """
        if not AIORTC_AVAILABLE:
            raise RuntimeError("aiortc is required for WebRTC support")

        self.on_audio = on_audio
        self.pc: Optional[RTCPeerConnection] = None
        self._closed = False
        self._consumer_tasks = set()
        self._pending_audio = []
        self._pending_samples = 0
        self._emit_samples = int(SAMPLE_RATE * 0.16)
        self._resampler = AudioResampler(
            format="fltp",
            layout="mono",
            rate=SAMPLE_RATE,
        )

    async def handle_offer(self, sdp: str) -> str:
        """
        Handle an SDP offer from the client.

        Returns the SDP answer string to send back.
        """
        self.pc = RTCPeerConnection()

        @self.pc.on("connectionstatechange")
        async def on_state():
            state = self.pc.connectionState
            logger.info(f"[WebRTC] Connection state: {state}")
            if state in ("failed", "closed"):
                await self.close()

        @self.pc.on("track")
        def on_track(track):
            logger.info(f"[WebRTC] Track received: {track.kind}")
            if track.kind == "audio":
                task = asyncio.create_task(self._consume_audio(track))
                self._consumer_tasks.add(task)
                task.add_done_callback(self._consumer_tasks.discard)

        # Set remote description (client's offer)
        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await self.pc.setRemoteDescription(offer)

        # Create and set local description (our answer)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)

        return self.pc.localDescription.sdp

    async def add_ice_candidate(self, candidate_dict: dict):
        """Add an ICE candidate from the client."""
        if not self.pc:
            return

        try:
            candidate_sdp = candidate_dict.get("candidate", "")
            if candidate_sdp.startswith("candidate:"):
                candidate_sdp = candidate_sdp[len("candidate:"):]
            candidate = candidate_from_sdp(candidate_sdp)
            candidate.sdpMid = candidate_dict.get("sdpMid")
            candidate.sdpMLineIndex = candidate_dict.get("sdpMLineIndex")
            await self.pc.addIceCandidate(candidate)
        except Exception as e:
            logger.warning(f"[WebRTC] Failed to add ICE candidate: {e}")

    async def _consume_audio(self, track):
        """
        Consume audio frames from WebRTC track.

        Resamples to 16kHz mono float32 and forwards to the session handler.
        """
        logger.info("[WebRTC] Starting audio consumption")

        try:
            while not self._closed:
                try:
                    frame: AudioFrame = await asyncio.wait_for(
                        track.recv(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    if not self._closed:
                        logger.info(f"[WebRTC] Audio track ended: {e}")
                    break

                # PyAV handles packed/planar layouts and performs stateful,
                # anti-aliased downmix + resampling from WebRTC's usual 48 kHz.
                for resampled_frame in self._resampler.resample(frame):
                    self._append_resampled_frame(resampled_frame)
                    if self._pending_samples >= self._emit_samples:
                        await self.flush_pending_audio()
        finally:
            # AudioResampler may retain a few delayed samples and the callback
            # aggregator can hold up to 159 ms. Deliver both when a track ends.
            try:
                for resampled_frame in self._resampler.resample(None):
                    self._append_resampled_frame(resampled_frame)
            except Exception as e:
                logger.warning(f"[WebRTC] Failed to flush resampler tail: {e}")
            await self.flush_pending_audio()
            logger.info("[WebRTC] Audio consumption ended")

    def _append_resampled_frame(self, frame):
        audio = frame.to_ndarray().reshape(-1).astype(np.float32, copy=False)
        if len(audio):
            self._pending_audio.append(audio)
            self._pending_samples += len(audio)

    async def flush_pending_audio(self):
        """Emit any aggregated PCM, including a tail shorter than 160 ms."""
        if not self._pending_audio:
            return

        chunk = np.concatenate(self._pending_audio)
        self._pending_audio = []
        self._pending_samples = 0
        try:
            await self.on_audio(chunk)
        except Exception as e:
            logger.error(f"[WebRTC] Audio handler error: {e}")

    async def close(self):
        """Close the peer connection."""
        if self._closed:
            return
        self._closed = True

        if self.pc:
            await self.pc.close()
            self.pc = None

        current = asyncio.current_task()
        consumers = {
            task for task in self._consumer_tasks
            if task is not current and not task.done()
        }
        if consumers:
            _, pending = await asyncio.wait(consumers, timeout=1.0)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        # Defensive fallback for a connection closed before a consumer task
        # was registered or after it exited between the checks above.
        await self.flush_pending_audio()

        logger.info("[WebRTC] Connection closed")

    @staticmethod
    def is_available() -> bool:
        """Check if WebRTC is available."""
        return AIORTC_AVAILABLE
