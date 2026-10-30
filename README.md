# PhoneMirror — Scrcpy GUI

A simple Windows GUI for mirroring and controlling Android devices with scrcpy.

## Features

### Core
- USB and Wi-Fi (ADB) device connection with automatic device detection
- Three-step workflow: Connect → Options → Start
- Quality presets (LOW / MEDIUM / HIGH) and expert settings tucked into an Advanced accordion
- Quick actions: Screenshot, Record, Fullscreen, Rotate, Stay Awake, Open Recordings folder
- Emergency kill switch that only stops processes started by this app instance

### Quick-Action Toggles
The QUICK ACTIONS panel includes three toggle buttons. Enabled toggles are highlighted green.

- **🔊 Audio** — Mirror the phone's internal audio (music, app sounds, game audio):
  - ON: internal audio is forwarded to the PC (`--audio-source output`;
    requires Android 11+); the phone's own speaker is muted while mirroring
  - OFF: no internal audio
  - Works with any source — screen, back camera, front camera. Fully
    independent of the Mic toggle.
- **🎤 Mic** — Turn microphone audio capture on/off independently:
  - ON + Audio ON: the microphone streams through a second, audio-only
    scrcpy process, so mic and phone audio play at the same time
  - ON + Audio OFF: the microphone is the main audio source (`--audio-source mic`)
  - OFF: no microphone
  - scrcpy cannot change its audio source while running, so toggling Mic
    with Audio off automatically restarts the session; with Audio on, the
    main session is never disturbed.
- **📌 On Top** — Overlay mode: pin the scrcpy window above all other windows:
  - While mirroring is running, the running window is pinned/unpinned immediately
    (no restart needed)
  - Otherwise the setting is remembered and applied as `--always-on-top` on the next start

### Advanced Settings (Expert)
Tabs for Video, Audio, Window, Device, Recording, and Performance — including codecs,
bitrate, resolution, orientation, display ID, view-only mode, custom scrcpy arguments,
and a recording folder/format selector that actually produces video files.

## Run

Double-click `START.bat`.

This source build requires Python 3. `adb.exe` and `scrcpy.exe` are bundled when available
from the previous package.

## Notes

- The UI and application logic are newly written. The scrcpy/ADB binaries are runtime
  dependencies, not the UI source.
- ADB/scrcpy output is logged to `scrcpy-error.log`; if a session ends unexpectedly the
  real error is shown in a dialog.
