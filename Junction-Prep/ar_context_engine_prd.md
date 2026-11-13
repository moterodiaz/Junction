# Product Requirements Document (PRD): Wearable AR Context Engine

## 1. Executive Summary & System Overview
The **Wearable AR Context Engine** is a real-time heads-up cognitive assistant designed for students, researchers, and engineers. Using a frame-mounted Raspberry Pi Camera and an I2S digital microphone paired with XREAL AR glasses, the system captures what the user is looking at—whether a textbook, archaic literature, a university lecture board, or handwritten derivations—and streams contextual explanations, mathematical verifications, and vocabulary annotations directly into the user's field of view using Anthropic’s Claude API.

---

## 2. End-to-End System Architecture

To eliminate continuous wireless video streaming overhead and avoid iOS captive-portal disconnects, the system uses an **Edge-Gated Event Architecture**. Rather than having the Raspberry Pi host a standalone Wi-Fi AP (which breaks the iPhone's cellular internet routing), the **iPhone acts as the Personal Hotspot** (with 2.4 GHz compatibility enabled). The Raspberry Pi joins the iPhone's network as a client, giving both devices a local IP bridge while keeping the iPhone's 5G/LTE connection alive for Claude API calls.

```text
[ WEARABLE HEAD UNIT (Pi Zero 2 W) ]                [ HOST COMPUTE (iPhone) ]                 [ CLOUD / DISPLAY ]
┌──────────────────────────────────┐               ┌─────────────────────────┐               ┌───────────────────┐
│ • Pi Camera (MIPI CSI-2)         │               │ • iOS Personal Hotspot  │               │ Anthropic API     │
│   └─> 320x240 Motion Gate (15Hz) │               │   (2.4GHz Compat Mode)  │               │ • Claude Sonnet   │
│   └─> 1080p Still Capture        │──WebSockets──>│                         │──HTTPS/SSE───>│ • Claude Haiku    │
│                                  │  (172.20.10.x)│ • Orchestrator App      │               └─────────┬─────────┘
│ • INMP441 Mic (I2S GPIO)         │               │   ├─ Local Whisper STT  │                         │
│   └─> 16kHz PCM Audio Stream     │               │   ├─ Prompt Router      │<──Token Delta Stream────┘
└──────────────────────────────────┘               │   └─ HUD UI Renderer    │
                                                   └────────────┬────────────┘
                                                                │ USB-C (DP Alt Mode)
                                                                ▼
                                                   ┌─────────────────────────┐
                                                   │ XREAL Air / One Glasses │
                                                   │ • 1080p Micro-OLED HUD  │
                                                   └─────────────────────────┘
```

### Data & Processing Pipeline
1. **Sensory Capture & Edge Gating (Raspberry Pi Zero 2 W):**
   * **Visual Motion Gate:** Captures low-resolution ($320 \times 240$) grayscale frames at $15\text{ Hz}$ into a memory buffer and calculates structural similarity (SSIM) or Mean Squared Error (MSE) between consecutive frames. When head movement stops for $>1.5\text{ seconds}$ (lecture board gaze, page turn completion) or a voice command occurs, the Pi captures a full-resolution $1920 \times 1080$ JPEG frame.
   * **Audio Capture:** The INMP441 I2S MEMS microphone captures $16\text{ kHz}$, 16-bit mono PCM audio. A lightweight local Voice Activity Detector (WebRTC VAD) streams audio packets over WebSockets only when speech is detected.
2. **Local Transport Layer:**
   * The Pi connects to the iPhone's Personal Hotspot (`172.20.10.x` subnet) and advertises its local WebSocket server via mDNS (`ar-capture.local:8765`).
3. **Orchestration & Intelligence (iPhone Host):**
   * **Speech-to-Text (STT):** Transcribes incoming voice packets on-device using Apple's `SFSpeechRecognizer` or local `whisper.cpp` (zero latency, zero API cost).
   * **Context & Prompt Routing:** Pairs the latest high-res JPEG with the transcribed voice prompt (or runs an autonomous "Passive Study" prompt if triggered by a page turn) and dispatches a streaming `POST` request to the Anthropic Messages API.
     * *Claude Haiku:* Used for fast, low-cost passive annotations (vocabulary definitions, quick date/reference lookups, foreign language translation).
     * *Claude Sonnet:* Triggered for complex analytical tasks (handwritten derivation verification, whiteboard equation steps, textbook diagram analysis, circuit/IC pinout lookup).
4. **HUD Rendering (XREAL Glasses):**
   * The iPhone drives the XREAL glasses as an external $1920 \times 1080$ display over USB-C DisplayPort Alt Mode.
   * The app renders a pure black background (`#000000` is completely transparent on XREAL's Micro-OLED optical combiners) with high-contrast peripheral text cards (`#00FFCC` or `#FFFFFF`) populated in real time via Server-Sent Events (SSE).

---

## 3. Bill of Materials (BOM) & Verified Sourcing Links

Assuming you already own the **XREAL Glasses**, **Pi Camera**, and **iPhone**, you need to source the following components. Every Amazon ASIN and backup search link below has been verified:

| Component | Technical Specification | Est. Price | Verified Amazon Link |
| :--- | :--- | :--- | :--- |
| **Compute Board** | Raspberry Pi Zero 2 W (Quad-core 1GHz, 512MB RAM, 2.4GHz Wi-Fi) | ~$25–$35 | [Direct Product Page (B0DRRRZBMP)](https://www.amazon.com/dp/B0DRRRZBMP) |
| **Camera Ribbon** | Arducam 22-Pin (0.5mm) to 15-Pin (1.0mm) Pi Zero Camera Cable Set | ~$8–$10 | [Direct Product Page (B085RW9K13)](https://www.amazon.com/dp/B085RW9K13) |
| **Digital Mic** | INMP441 Omnidirectional MEMS I2S Interface Microphone Module | ~$8–$12 | [Direct Product Page (B0C1C64R8S)](https://www.amazon.com/dp/B0C1C64R8S) |
| **Power Booster** | Adafruit PowerBoost 500 Basic (3.7V LiPo to 5.2V USB Boost Converter) | ~$12–$15 | [Direct Product Page (B07JQ1QFGK)](https://www.amazon.com/dp/B07JQ1QFGK) |
| **LiPo Battery** | EEMB 3.7V 2000mAh 103454 LiPo Rechargeable Battery w/ JST PH2.0 | ~$11–$14 | [Direct Product Page (B0B7N2T1TD)](https://www.amazon.com/dp/B0B7N2T1TD) |
| **Storage** | SanDisk Ultra 32GB Class 10 A1 microSDHC UHS-I Card | ~$9–$13 | [Direct Product Page (B010Q57T02)](https://www.amazon.com/dp/B010Q57T02) |
| **Charge & Play** | XREAL Hub (Splits iPhone USB-C into 1080p DP Alt Mode + 45W PD) | ~$40 | [Amazon Search: XREAL Hub Adapter](https://www.amazon.com/s?k=XREAL+Hub+Power+and+Play+Adapter) |
| **Thermal (Opt.)** | 14x14mm Copper Heatsink w/ Thermal Conductive Adhesive Tape | ~$6–$8 | [Amazon Search: 14x14mm Pi Zero Heatsink](https://www.amazon.com/s?k=14x14mm+copper+heatsink+raspberry+pi+zero) |

---

## 4. Custom Engineering Deliverables (What Needs to Be Created)

### A. Mechanical & CAD Deliverables (3D Printed)
1. **Temple/Bridge Camera Clip (PETG or TPU 95A):**
   * A snap-fit bracket attaching the Pi Camera module to the center bridge or right temple arm of the XREAL frames.
   * **Design Constraint:** Angle the camera downward by $12^\circ\text{ to }15^\circ$ below the horizontal horizon so the camera naturally centers on desk-level textbooks and notebooks without forcing the user to crane their neck downward.
2. **Collar/Pocket Compute Pod (PLA/PETG):**
   * Rather than mounting the battery and Pi Zero 2 W on the frames (which adds $\sim 65\text{ g}$ of unbalanced weight and heat against the temple), house the Pi Zero 2 W, PowerBoost 500, and $2000\text{ mAh}$ LiPo in a vented clip-on collar pod (using the $15\text{ cm}$ CSI ribbon cable clipped along the glasses tether).

### B. Embedded Daemon (Raspberry Pi Python Service)
* **`capture_daemon.py`:** A `systemd` background service managing two concurrent threads:
  * **Thread 1 (Vision):** Interfaces with `Picamera2` to run the $320 \times 240$ motion-differencing gate and pull $1080\text{p}$ JPEG buffers on stillness or manual voice command.
  * **Thread 2 (Audio):** Reads raw PCM chunks from the ALSA `snd_rpi_i2s_card` device, runs `webrtcvad` to strip silence, and pushes active speech frames + trigger snapshots over an `asyncio` WebSocket server.

### C. Host Application & HUD Renderer (iPhone)
* **External Display Canvas (SwiftUI or Unity WebGL):**
  * Uses `UIScreen.screens` (SwiftUI) to detect when the XREAL glasses are plugged in and launches a dedicated $1920 \times 1080$ window on the secondary display while keeping the iPhone screen as a touch trackpad and mode selector.
  * **HUD Layout Zones:**
    * *Top-Right Periphery (35% width):* Rolling streaming output for Claude text definitions, lecture bullet summaries, and step-by-step equation checks (rendered via KaTeX/MathJax).
    * *Bottom-Left Status Pill:* Connection heartbeat indicator, active mode (`Lecture` | `Book` | `Notes`), and microphone listening state.

---

## 5. Step-by-Step Setup & Integration Guide

> **WARNING — LiPo Battery & GPIO Soldering Safety:**
> Disconnect the $3.7\text{ V}$ LiPo battery from the PowerBoost 500 before soldering GPIO connections. Verify battery connector polarity before plugging into the PowerBoost JST header (some third-party JST batteries reverse the red/black wires). Ensure the INMP441 `VDD` pin is wired strictly to the Pi's **$3.3\text{ V}$** rail (Pin 1)—connecting it to the $5\text{ V}$ rail will permanently destroy the microphone.

### Phase 1: Hardware & I2S Audio Wiring
1. **Connect the Camera Ribbon:** Attach the 22-pin narrow end of the CSI cable to the Pi Zero 2 W (metal contacts facing **down** toward the PCB) and the 15-pin wide end to the Pi Camera.
2. **Solder the INMP441 Microphone to the Pi Zero 2 W GPIO:**
   * `VDD` $\rightarrow$ **Pin 1** ($3.3\text{ V}$)
   * `GND` $\rightarrow$ **Pin 6** (GND)
   * `SCK` (Serial Clock) $\rightarrow$ **Pin 12** (GPIO 18 / PCM_CLK)
   * `WS` (Word Select) $\rightarrow$ **Pin 35** (GPIO 19 / PCM_FS)
   * `SD` (Serial Data) $\rightarrow$ **Pin 38** (GPIO 20 / PCM_DIN)
   * `L/R` (Left/Right Channel) $\rightarrow$ **Pin 9** (GND — sets microphone to Left channel mono)
3. **Wire Power Supply:** Solder the `5V` and `GND` output pads of the Adafruit PowerBoost 500 to **Pin 2** ($5\text{ V}$) and **Pin 4** (GND) on the Pi (or connect via a short Micro-USB cable to the Pi's `PWR IN` port).

*Verification:* Plug the LiPo battery into the PowerBoost JST port. The PowerBoost blue $5\text{ V}$ LED and the Pi Zero green activity LED should illuminate immediately.

### Phase 2: Headless OS & Network Configuration
1. **Flash OS:** Using Raspberry Pi Imager, flash **Raspberry Pi OS Lite (64-bit, Debian Bookworm)** onto the 32GB MicroSD card.
2. **Pre-Configure Hotspot Client:** In the Imager OS Customization settings:
   * Set Hostname: `ar-capture.local`
   * Enable SSH (password or public key).
   * Enter your **iPhone Personal Hotspot SSID and Password**.
3. **Prepare iPhone Hotspot:** On your iPhone, navigate to **Settings $\rightarrow$ Personal Hotspot** and toggle **Maximize Compatibility** to **ON** (forces $2.4\text{ GHz}$ broadcast so the Pi Zero 2 W can connect).
4. **Disable Wi-Fi Power Management & Enable I2S:** SSH into the Pi (`ssh pi@ar-capture.local`) and edit `/boot/firmware/config.txt` to enable the I2S bus:
   ```bash
   dtparam=i2s=on
   dtoverlay=googlevoicehat-soundcard
   ```
   Then disable wireless sleep so the stream never drops during silent reading:
   ```bash
   sudo nmcli connection modify "preconfigured" 802-11-wireless.powersave 2
   ```

*Verification:* Reboot the Pi and run `arecord -l`. You should see the I2S soundcard listed as `card 0`. Run `rpicam-still -o test.jpg` to confirm the camera ribbon is seated properly.

### Phase 3: Edge Daemon & Claude Pipeline Deployment
1. **Install Dependencies on Pi:**
   ```bash
   sudo apt update && sudo apt install -y python3-picamera2 python3-opencv python3-websockets python3-pyaudio
   ```
2. **Deploy Capture Script:** Configure your Python daemon to listen on port `8765`, streaming base64-encoded $1080\text{p}$ JPEG frames whenever motion drops below threshold or audio speech ends.
3. **Connect XREAL Glasses & Launch Host App:** Plug the XREAL glasses into the iPhone (via the XREAL Hub for external battery power), connect the app's WebSocket client to `ws://ar-capture.local:8765`, and input your Anthropic API key.

*Verification:* Look at a page of notes and ask a question aloud. Within 1 second, the HUD status pill should change to `Streaming...` and Claude's response tokens should populate in the upper-right glass display.

---

## 6. Multi-Scenario Operating Modes

| Operating Mode | Trigger Mechanism | Target Claude Model | System Prompt Behaviour & HUD Output |
| :--- | :--- | :--- | :--- |
| **1. Immersive Book Mode** | Passive Stillness ($>1.5\text{ s}$) + Optional Voice | `claude-3-5-haiku` | Extracts archaic/complex idioms, historical references, and character callbacks; displays 3 concise footnote bullets in top-right HUD. |
| **2. Lecture & Whiteboard Mode** | Voice Trigger or Manual Tap on Phone | `claude-3-5-sonnet` | Transcribes dense board diagrams/slides, defines domain-specific acronyms, and summarizes the professor's spoken context. |
| **3. Math & Note Verification** | Voice: *"Check my derivation"* | `claude-3-5-sonnet` | Parses handwritten calculus/physics steps, checks for sign or integration errors, and renders LaTeX corrections step-by-step. |
| **4. Lab & Hardware Bench** | Voice: *"Show pinout for this chip"* | `claude-3-5-sonnet` | Reads IC package markings or resistor codes and projects a pinout reference table and operating voltage summary. |

---

## 7. Potential Issues & Troubleshooting Matrix

| Failure Mode / Issue | Root Cause | Engineering Mitigation / Fix |
| :--- | :--- | :--- |
| **Blurry Near-Field Text (Books/Notes)** | Standard Pi Camera v1/v2 lenses are factory-glued at a fixed hyperfocal distance ($\sim 1\text{ m}$ to infinity), making text at $35\text{ cm}$ blurry. | **Mechanical Fix:** Use fine tweezers to break the tiny glue spots on the camera lens barrel and rotate the lens **counter-clockwise $90^\circ\text{ to }120^\circ$** to bring the focal plane to $35\text{ cm}$. |
| **Parallax & FOV Offset** | The camera sits $25\text{ mm}$ to the side of your dominant eye; what sits in the center of your vision is off-center in the camera frame. | **Software Calibration:** Build a 1-time "Calibration Crosshair" mode in the HUD. Hold a target card at $40\text{ cm}$, align it with the HUD crosshair, and apply a static 2D crop offset to the Pi camera capture region. |
| **Motion Blur on Capture** | Slight head micro-movements during indoor low-light lectures cause smeared text on whiteboard or book captures. | **Exposure Clamping:** In `Picamera2`, clamp maximum shutter exposure time to $8000\text{ }\mu\text{s}$ ($1/125\text{ s}$) and allow analog gain (ISO) to float up. Noise never breaks Claude's vision OCR, whereas motion blur destroys legibility. |
| **iPhone Hotspot Auto-Disconnects** | iOS turns off Personal Hotspot broadcasting after 90 seconds if no device is actively connected. | **Boot Order & Keepalive:** Toggle "Allow Others to Join" off/on on the iPhone right as you power on the Pi. Once connected, have the Pi send a 1-byte WebSocket ping every 5 seconds to keep the interface active. |
| **High Token Drain / API Rate Limits** | Continuous page scanning or jittery motion detection triggers excessive $1080\text{p}$ image uploads to Claude. | **pHash Deduplication + Downscaling:** Resize captured images to $1568 \times 882$ (Anthropic's optimal internal vision scaling limit) and compute a Perceptual Hash (`imagehash`). Do not fire a new passive request unless the page content has changed by $>25\%$. |
| **Pi Zero 2 W Thermal Throttling** | Running continuous OpenCV frame differencing + Wi-Fi transmission in an enclosed 3D-printed case pushes CPU temps past $80^\circ\text{C}$. | **Downsampled Diffing + Heatsink:** Stick a $14 \times 14\text{ mm}$ copper heatsink on the Pi Zero SoC, add ventilation slots to your CAD enclosure, and run the motion gate strictly on the hardware-accelerated `lores` ($320 \times 240$ YUV) stream rather than decoding full $1080\text{p}$ frames. |