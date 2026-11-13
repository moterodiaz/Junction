# Junction-Prep: Summary

Ported from `Junction-Prep` repo. Full spec: [ar_context_engine_prd.md](ar_context_engine_prd.md).

## What
Wearable AR Context Engine: heads-up study assistant for students, researchers and engineers. A frame-mounted Pi camera and I2S mic feed Claude. Explanations, math checks and vocabulary notes appear on XREAL AR glasses.

## Architecture (edge-gated events)
- **Head unit (Pi Zero 2 W):** 320x240 grayscale motion gate at 15 Hz (SSIM/MSE). Stillness over 1.5 s triggers a 1080p JPEG. INMP441 mic at 16 kHz with WebRTC VAD streams speech only.
- **Transport:** Pi joins iPhone Personal Hotspot (2.4 GHz compat mode). WebSocket at `ar-capture.local:8765`.
- **Host (iPhone):** On-device STT (`SFSpeechRecognizer` or `whisper.cpp`). Routes image + prompt to Anthropic Messages API: Haiku for passive annotations, Sonnet for analytical tasks.
- **HUD:** SwiftUI/Unity canvas over USB-C DP Alt Mode. Black background, `#00FFCC`/`#FFFFFF` text, SSE streaming, KaTeX for math. Top-right output zone, bottom-left status pill.

## Deliverables
- 3D-printed camera clip (12-15 degree downward tilt) and collar compute pod (PETG/TPU).
- `capture_daemon.py`: systemd service, vision thread (`Picamera2`) + audio thread (`webrtcvad`, ALSA), asyncio WebSocket server.
- iPhone host app with external-display HUD and phone-side mode selector.

## BOM
About $120-150 (Pi Zero 2 W, Arducam cable, INMP441, PowerBoost 500, 2000 mAh LiPo, microSD, XREAL Hub, heatsink). Glasses and phone assumed owned.

## Modes
| Mode | Model | Trigger |
|---|---|---|
| Immersive Book | Haiku | Stillness, optional voice |
| Lecture / Whiteboard | Sonnet | Voice or phone tap |
| Math / Note Verification | Sonnet | "Check my derivation" |
| Lab / Hardware Bench | Sonnet | "Show pinout for this chip" |

## Top Risks
Fixed-focus lens blur, camera parallax offset, motion blur (clamp exposure to 8 ms), hotspot auto-disconnect (5 s WebSocket keepalive), token drain (pHash dedupe, resize to 1568x882), Pi thermal throttling (downsampled diffing + heatsink).

## Notes
- PRD uses `claude-3-5-haiku` / `claude-3-5-sonnet`. Outdated; swap in current Haiku/Sonnet IDs.
- Source PRD text is partly garbled in places (missing words, broken tables). Re-check wiring and BOM sections before building.
