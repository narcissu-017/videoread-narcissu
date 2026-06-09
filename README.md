# VideoRead

[![English](https://img.shields.io/badge/README-English-2d6cdf?style=for-the-badge)](README.md) [![简体中文](https://img.shields.io/badge/%E8%AF%B4%E6%98%8E-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-2d6cdf?style=for-the-badge)](README.zh-CN.md)

VideoRead is a multi-window tiled video player for reviewing many clips at once.

Current version: `v0.9`

It works especially well when you want to:
- compare multiple short videos or clips side by side
- mix horizontal and vertical videos in the same workspace
- preserve order, aspect ratio, and make good use of screen space
- save reusable video sets as templates
- and, honestly, use your giant screen to tile your hand-picked clips so you can get going right away

## Features
- Multiple video window groups at the same time
- Silent looping playback by default
- Drag and drop video import
- Fixed-row layout and smart layout
- Drag to reorder videos inside a group
- Per-video hover controls: play/pause, mute, progress, volume
- Template library, history, and session saving
- Open, update, reload, and delete templates
- Batch remove videos
- System playback mode and optional VLC playback mode

## What's New in v0.9
Compared with v0.8, this version adds and improves:
- Optional playback backend selection between system mode and VLC mode
- Per-video progress control in the hover overlay
- Restart all videos from the beginning from the window context menu
- Multi-select, deselect, and batch remove inside a video group
- Window-level context menu actions for saving, updating, and reloading templates
- Better mixed horizontal/vertical video layout and cross-DPI screen movement handling
- Safer cleanup when reloading templates or removing videos

## Download and Use
A ready-to-run build is included in this repository:
- `dist/VideoRead.exe`

Usage notes:
- Running the EXE does not require Python to be installed.
- On first launch, the app creates its own local state folder under `dist/state/`.
- It is best to keep and move the whole `dist` folder together.

Playback notes:
- Common `mp4`, `mkv`, `webm`, `mov`, and `avi` files should work in most cases.
- If some files do not play correctly, `mp4` files encoded with `H.264 + AAC` are usually the safest choice.
- System mode uses the local Windows/Qt multimedia environment.
- VLC mode can be selected in the app when a compatible VLC/libVLC runtime is available.
- If VLC mode is not available, VideoRead can still be used in system mode.

## Run from Source
Environment:
- Windows 10/11
- Python 3.12 or a nearby version

Install dependencies:
```powershell
python -m pip install -r requirements.txt
```

Optional VLC mode:
- Install VLC on Windows, or place a compatible `libVLC/` or `vlc_runtime/` folder next to `app.py`.
- The source repository does not include local runtime bundles or personal state data.

Run:
```powershell
python app.py
```

Or double-click:
- `start_videoread.bat`

## Basic Usage
1. Start the app and create a window group.
2. Drag videos into the group, or import them through the UI.
3. Switch between fixed layout and smart layout as needed.
4. Hover over a video to show the minimal overlay controls.
5. Drag videos inside a group to reorder them.
6. Save a template if you want to reopen the same set later.

## Templates and History
- Templates are useful for saving common video sets, order, algorithm choice, and layout settings.
- History is useful for restoring recent working states.
- These are stored locally in the `state/` folder and do not modify the original files.

## Layout Algorithm Notes
This repository includes a separate layout algorithm document:
- `docs/layout_algorithms.md`

It explains the current layout strategies, their goals, and the core implementation ideas with code snippets.

## Feedback and Algorithm Improvements
The current smart layout is already practical for daily use, but there is still room for improvement, especially around:
- space utilization for mixed horizontal and vertical videos
- stability when many videos are playing at once
- more natural layouts under very different window sizes
- better readability and density for larger batches

If anyone would like to help improve the layout algorithms even further, suggestions and contributions are very welcome.
