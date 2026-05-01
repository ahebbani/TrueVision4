# Production Checkpoints

This document tracks the hardware validation points that should pass before moving deeper into the stack. Update it each time a new subsystem lands.

## Current Slice: Pi Runtime + Display

### Checkpoint 1: Foundation Ready
- Run `make setup-pi`.
- Confirm [data/faces.db](/Users/adity/Files/TrueVision4/data/faces.db) and [logs](/Users/adity/Files/TrueVision4/logs) are created.
- Run `make checkpoints` with the Pi app stopped.
- Expected result: local file checks pass, controller checks are unreachable, which is acceptable before runtime launch.

### Checkpoint 2: Black HUD Mode
- Run `make run` on the Pi HDMI output.
- Confirm the controller is reachable at `http://<pi-ip>:8080/`.
- Confirm [data/runtime/latest-hud.jpg](/Users/adity/Files/TrueVision4/data/runtime/latest-hud.jpg) and [data/runtime/latest-hud.json](/Users/adity/Files/TrueVision4/data/runtime/latest-hud.json) are updating.
- Expected result: `/api/runtime/status` reports `display_background=black`, `snapshot_ready=true`, and `snapshot_pipeline=pass`.

### Checkpoint 3: Camera HUD Mode
- Run `make run-display` on the Pi.
- Open `/api/runtime/status` and verify `display_background=camera`.
- Confirm `camera_backend` is `picamera2` or `opencv`, not `mock`.
- Expected result: `camera_background=pass`. If it is `warn`, the app fell back to the simulator and the camera path is not production-ready yet.

### Checkpoint 4: Controller Integration
- Open the phone controller and toggle FACE, AUDIO, and BOTH.
- Open a launcher and then close it.
- Add a reminder and a face from the phone UI.
- Expected result: `/api/status` and `/api/runtime/status` reflect the changes immediately and the HUD snapshot updates to show reminders and launcher state.

## Current Slice: Audio, Face, and Server Flow

### Checkpoint 5: AUDIO Meeting Lifecycle
- Run `make run`.
- Switch to AUDIO mode from the phone controller.
- Leave the system in AUDIO mode for at least 1 second so a WAV is written.
- Switch back to FACE mode.
- Expected result: [data/faces.db](/Users/adity/Files/TrueVision4/data/faces.db) contains a completed meeting, `/api/runtime/status` shows non-zero `audio_buffer_duration_sec` during capture, and `/api/meetings` shows a summary after the session ends.

### Checkpoint 6: Face Enrollment and Presence
- Use the phone controller Add Face section while the camera can see a face.
- Expected result: the new face appears in `/api/faces`, a face embedding record exists, and the HUD center zone shows the enrolled name on the next render cycle.

### Checkpoint 7: Server Offload
- Start the server with `make run-server`.
- Start the Pi app with `TRUEVISION_SERVER_URL=http://<server-ip>:8008 make run-display`.
- Switch to BOTH mode.
- Expected result: `/api/runtime/status` reports `server_connected=true`, captions are driven by the server WebSocket route, and ending a session yields a server-generated transcript and summary.

## Ongoing Hardware Gates

### Audio / UART Slice
- Validate ESP32 packet parsing, UART reconnects, and a rolling audio buffer on the Pi.
- Production gate: the Pi must ingest real UART packets continuously for at least 5 minutes without parser drift or checksum failures.

### Live Caption Slice
- Validate local caption updates in AUDIO mode and server-offloaded captions in BOTH mode.
- Production gate: captions must remain legible and refresh continuously while the HUD and controller stay responsive.

### Face Recognition Slice
- Validate real detections, recognition, presence transitions, and meeting lifecycle start/stop behavior.
- Production gate: repeated entries and exits of the same person must update the overlay and meeting records without duplicate-session churn.

### Server Offload Slice
- Validate `/health`, `/ws/audio`, `/summarize`, translation, and Telegram on the GPU server.
- Production gate: the Pi must auto-upgrade to BOTH when the server is reachable and fall back cleanly when it disappears.

### Deployment Slice
- Validate [deploy/systemd/truevision.service](/Users/adity/Files/TrueVision4/deploy/systemd/truevision.service) and [deploy/systemd/truevision-server.service](/Users/adity/Files/TrueVision4/deploy/systemd/truevision-server.service) on the target hosts.
- Production gate: rebooting the Pi and server should bring both services back without manual intervention.

