# VideoRead

[![English](https://img.shields.io/badge/README-English-2d6cdf?style=for-the-badge)](README.md) [![简体中文](https://img.shields.io/badge/%E8%AF%B4%E6%98%8E-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-2d6cdf?style=for-the-badge)](README.zh-CN.md)

VideoRead is a multi-window tiled video player for reviewing many clips at once.

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
- Playback behavior can still depend on the system multimedia environment and the actual codec used by the file.

## Run from Source
Environment:
- Windows 10/11
- Python 3.12 or a nearby version

Install dependencies:
```powershell
python -m pip install -r requirements.txt
```

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
