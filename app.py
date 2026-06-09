
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

if getattr(sys, "frozen", False):
    _EARLY_APP_DIR = Path(sys.executable).resolve().parent
    _EARLY_RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", _EARLY_APP_DIR)).resolve()
else:
    _EARLY_APP_DIR = Path(__file__).resolve().parent
    _EARLY_RESOURCE_DIR = _EARLY_APP_DIR


def _early_candidate_vlc_dirs() -> list[Path]:
    candidates = [
        _EARLY_RESOURCE_DIR / "vlc_runtime",
        _EARLY_RESOURCE_DIR / "libVLC",
        _EARLY_APP_DIR / "vlc_runtime",
        _EARLY_APP_DIR / "libVLC",
    ]
    for env_name in ("VIDE0READ_VLC_DIR", "VIDEOREAD_VLC_DIR", "VLC_DIR"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            candidates.append(Path(raw))
    if sys.platform.startswith("win"):
        candidates.extend(
            [
                Path(r"C:\Program Files\VideoLAN\VLC"),
                Path(r"C:\Program Files (x86)\VideoLAN\VLC"),
            ]
        )
    seen: set[str] = set()
    out: list[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _preload_vlc_runtime_for_import() -> None:
    for candidate in _early_candidate_vlc_dirs():
        if not candidate.exists():
            continue
        plugin_dir = candidate / "plugins"
        if plugin_dir.exists():
            os.environ.setdefault("VLC_PLUGIN_PATH", str(plugin_dir))
        if sys.platform.startswith("win"):
            try:
                os.add_dll_directory(str(candidate))
            except Exception:
                pass
        break


_preload_vlc_runtime_for_import()

try:
    import av
except Exception:
    av = None

try:
    import vlc
except Exception:
    vlc = None

from PyQt5.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QCursor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QMediaPlaylist
from PyQt5.QtMultimediaWidgets import QVideoWidget
try:
    from PyQt5 import sip
except Exception:
    sip = None

APP_VERSION = "0.9"
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".ts", ".flv"}
LAYOUT_ALGOS = {"grid": "算法1", "justified": "算法2"}
PLAYBACK_BACKENDS = {
    "qt": "系统模式 (Qt/本机)",
    "vlc": "独立模式 (VLC)",
}
VLC_QUIET_ARGS = (
    "--quiet",
    "--verbose=-1",
    "--no-video-title-show",
    "--no-stats",
)

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR

ASSETS_DIR = RESOURCE_DIR / "assets"
APP_ICON_PNG = ASSETS_DIR / "videoread_icon.png"
APP_ICON_ICO = ASSETS_DIR / "videoread_icon.ico"
STATE_DIR = APP_DIR / "state"
TEMPLATE_DIR = STATE_DIR / "templates"
HISTORY_DIR = STATE_DIR / "history"
SESSION_FILE = STATE_DIR / "session.json"
_APP_ICON_CACHE: Optional[QIcon] = None
_VLC_RUNTIME_OK: Optional[bool] = None
_VLC_RUNTIME_READY = False
_SHARED_VLC_INSTANCE = None
_SHARED_VLC_LOG_CALLBACK = None


def ensure_dirs() -> None:
    for directory in (STATE_DIR, TEMPLATE_DIR, HISTORY_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_app_icon() -> QIcon:
    global _APP_ICON_CACHE
    if _APP_ICON_CACHE is None:
        icon_path = APP_ICON_PNG if APP_ICON_PNG.exists() else APP_ICON_ICO
        _APP_ICON_CACHE = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    return _APP_ICON_CACHE


def apply_window_icon(widget: QWidget) -> None:
    icon = load_app_icon()
    if not icon.isNull():
        widget.setWindowIcon(icon)


def playback_backend_label(key: str) -> str:
    return PLAYBACK_BACKENDS.get(key, PLAYBACK_BACKENDS["qt"])


def playback_backend_from_label(text: str) -> str:
    return "vlc" if "VLC" in str(text) else "qt"


def _candidate_vlc_runtime_dirs() -> list[Path]:
    candidates = [
        RESOURCE_DIR / "vlc_runtime",
        RESOURCE_DIR / "libVLC",
        APP_DIR / "vlc_runtime",
        APP_DIR / "libVLC",
    ]
    for env_name in ("VIDE0READ_VLC_DIR", "VIDEOREAD_VLC_DIR", "VLC_DIR"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            candidates.append(Path(raw))
    if sys.platform.startswith("win"):
        candidates.extend(
            [
                Path(r"C:\Program Files\VideoLAN\VLC"),
                Path(r"C:\Program Files (x86)\VideoLAN\VLC"),
            ]
        )
    seen: set[str] = set()
    out: list[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def prepare_vlc_runtime() -> Optional[Path]:
    global _VLC_RUNTIME_READY
    if _VLC_RUNTIME_READY:
        for candidate in _candidate_vlc_runtime_dirs():
            if candidate.exists():
                return candidate
        return None
    for candidate in _candidate_vlc_runtime_dirs():
        if not candidate.exists():
            continue
        plugin_dir = candidate / "plugins"
        if plugin_dir.exists():
            os.environ["VLC_PLUGIN_PATH"] = str(plugin_dir)
        if sys.platform.startswith("win"):
            try:
                os.add_dll_directory(str(candidate))
            except Exception:
                pass
        _VLC_RUNTIME_READY = True
        return candidate
    return None


def is_vlc_runtime_available() -> bool:
    global _VLC_RUNTIME_OK
    if _VLC_RUNTIME_OK is not None:
        return _VLC_RUNTIME_OK
    if vlc is None:
        _VLC_RUNTIME_OK = False
        return False
    try:
        shared_vlc_instance()
        _VLC_RUNTIME_OK = True
    except Exception:
        _VLC_RUNTIME_OK = False
    return _VLC_RUNTIME_OK


def attach_silent_vlc_log(instance) -> Optional[object]:
    if vlc is None:
        return None
    try:
        callback_type = getattr(vlc, "LogCb", None)
        if callback_type is None:
            callback_type = vlc.CallbackDecorators.LogCb

        @callback_type
        def _silent_log(_data, _level, _ctx, _fmt, _args) -> None:
            return None

        instance.log_set(_silent_log, None)
        return _silent_log
    except Exception:
        return None


def shared_vlc_instance():
    global _SHARED_VLC_INSTANCE, _SHARED_VLC_LOG_CALLBACK
    if vlc is None:
        raise RuntimeError("python-vlc 未安装。")
    if _SHARED_VLC_INSTANCE is not None:
        return _SHARED_VLC_INSTANCE
    prepare_vlc_runtime()
    instance = vlc.Instance(*VLC_QUIET_ARGS)
    if instance is None:
        raise RuntimeError("VLC 初始化失败。")
    _SHARED_VLC_INSTANCE = instance
    _SHARED_VLC_LOG_CALLBACK = attach_silent_vlc_log(instance)
    return _SHARED_VLC_INSTANCE


def sanitize_template_name(name: str) -> str:
    safe = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", name.strip())
    return safe or "template"


def geometry_string(widget: QWidget) -> str:
    geo = widget.geometry()
    return f"{geo.width()}x{geo.height()}+{geo.x()}+{geo.y()}"


def apply_geometry(widget: QWidget, value: str) -> None:
    m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", value.strip())
    if not m:
        return
    w, h, x, y = map(int, m.groups())
    widget.setGeometry(x, y, max(240, w), max(180, h))


def ffprobe_video_info(path: Path) -> tuple[int, int, int]:
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,side_data_list:stream_tags=rotate",
            "-of", "json",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=6)
        if result.returncode != 0 or not result.stdout.strip():
            return 0, 0, 0
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        if not streams:
            return 0, 0, 0
        stream = streams[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        rotate = 0
        tags = stream.get("tags") or {}
        rotate_raw = str(tags.get("rotate", "0") or "0").strip()
        try:
            rotate = int(float(rotate_raw)) % 360
        except Exception:
            rotate = 0
        for side in stream.get("side_data_list") or []:
            side_rotation = side.get("rotation")
            if side_rotation is not None:
                try:
                    rotate = int(float(side_rotation)) % 360
                    break
                except Exception:
                    pass
        return width, height, rotate
    except Exception:
        return 0, 0, 0


@dataclass
class VideoItem:
    path: Path
    width: int = 16
    height: int = 9
    duration_ms: int = 0


class TemplateInfoDialog(QDialog):
    def __init__(self, parent: QWidget, name: str, category: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("保存模板")
        self.setModal(True)
        self.resize(420, 160)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(name)
        self.category_edit = QLineEdit(category)
        self.category_edit.setPlaceholderText("可留空")
        form.addRow("模板名称", self.name_edit)
        form.addRow("分类/标签", self.category_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.category_edit.text().strip()


class MediaBackendBase(QObject):
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    errorOccurred = pyqtSignal(str)
    backend_key = "base"

    def __init__(self, parent: QWidget, path: Path) -> None:
        super().__init__(parent)
        self.path = path
        self.video_widget: QWidget = QWidget(parent)

    def play(self) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def set_muted(self, muted: bool) -> None:
        raise NotImplementedError

    def set_volume(self, volume: int) -> None:
        raise NotImplementedError

    def set_position(self, position_ms: int) -> None:
        raise NotImplementedError

    def position(self) -> int:
        raise NotImplementedError

    def duration(self) -> int:
        raise NotImplementedError

    def restart_playback(self) -> None:
        self.set_position(0)
        self.play()

    def rebind_output(self) -> None:
        return


class QtMediaBackend(MediaBackendBase):
    backend_key = "qt"

    def __init__(self, parent: QWidget, path: Path) -> None:
        super().__init__(parent, path)
        self._closed = False
        self.video_widget = QVideoWidget(parent)
        self.video_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        self.playlist = QMediaPlaylist(self)
        self.playlist.addMedia(QMediaContent(QUrl.fromLocalFile(str(path))))
        self.playlist.setPlaybackMode(QMediaPlaylist.Loop)
        self.player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
        self.player.setPlaylist(self.playlist)
        self.player.setVideoOutput(self.video_widget)
        self.player.setMuted(True)
        self.player.setVolume(0)
        self.player.error.connect(self._on_player_error)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.play()

    def _is_closed_or_deleted(self) -> bool:
        if self._closed:
            return True
        if sip is None:
            return False
        try:
            return bool(sip.isdeleted(self))
        except Exception:
            return True

    def _on_player_error(self, *_args) -> None:
        if not self._is_closed_or_deleted():
            self.errorOccurred.emit("播放失败")

    def _on_position_changed(self, value: int) -> None:
        if not self._is_closed_or_deleted():
            self.positionChanged.emit(max(0, int(value)))

    def _on_duration_changed(self, value: int) -> None:
        if not self._is_closed_or_deleted():
            self.durationChanged.emit(max(0, int(value)))

    def play(self) -> None:
        if self._is_closed_or_deleted():
            return
        self.player.play()

    def pause(self) -> None:
        if self._is_closed_or_deleted():
            return
        self.player.pause()

    def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.player.positionChanged.disconnect(self._on_position_changed)
        except Exception:
            pass
        try:
            self.player.durationChanged.disconnect(self._on_duration_changed)
        except Exception:
            pass
        try:
            self.player.error.disconnect(self._on_player_error)
        except Exception:
            pass
        try:
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.setPlaylist(None)
        except Exception:
            pass

    def set_muted(self, muted: bool) -> None:
        if self._is_closed_or_deleted():
            return
        self.player.setMuted(bool(muted))

    def set_volume(self, volume: int) -> None:
        if self._is_closed_or_deleted():
            return
        self.player.setVolume(max(0, min(100, int(volume))))

    def set_position(self, position_ms: int) -> None:
        if self._is_closed_or_deleted():
            return
        self.player.setPosition(max(0, int(position_ms)))

    def position(self) -> int:
        if self._is_closed_or_deleted():
            return 0
        return max(0, int(self.player.position()))

    def duration(self) -> int:
        if self._is_closed_or_deleted():
            return 0
        return max(0, int(self.player.duration()))


class VlcMediaBackend(MediaBackendBase):
    backend_key = "vlc"
    _start_counter = 0

    def __init__(self, parent: QWidget, path: Path) -> None:
        super().__init__(parent, path)
        if not is_vlc_runtime_available():
            raise RuntimeError("VLC 运行库不可用，请安装 VLC 或在发布版中携带 libVLC。")
        prepare_vlc_runtime()
        self._closed = False
        self.video_widget = QWidget(parent)
        self.video_widget.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.video_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.video_widget.setAutoFillBackground(True)
        palette = self.video_widget.palette()
        palette.setColor(QPalette.Window, QColor("#000000"))
        self.video_widget.setPalette(palette)
        self._instance = shared_vlc_instance()
        self._media = self._instance.media_new(str(path))
        if self._media is None:
            raise RuntimeError("VLC 无法创建媒体对象。")
        try:
            self._media.add_option("input-repeat=65535")
        except Exception:
            pass
        self._player = self._instance.media_player_new()
        if self._player is None:
            raise RuntimeError("VLC 无法创建播放器对象。")
        self._player.set_media(self._media)
        self._muted = True
        self._volume = 0
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_state)
        self._last_duration = 0
        self._bound = False
        VlcMediaBackend._start_counter += 1
        start_delay = ((VlcMediaBackend._start_counter - 1) % 24) * 120
        QTimer.singleShot(start_delay, self._start)

    def _start(self) -> None:
        if self._closed:
            return
        self.rebind_output()
        self.set_muted(True)
        self.set_volume(0)
        self.play()
        self._poll_timer.start(450)

    def _poll_state(self) -> None:
        if self._closed or self._player is None:
            return
        try:
            duration = max(0, int(self._player.get_length()))
            position = max(0, int(self._player.get_time()))
            if duration != self._last_duration:
                self._last_duration = duration
                self.durationChanged.emit(duration)
            self.positionChanged.emit(position)
            state = self._player.get_state()
            if state == vlc.State.Ended:
                self._player.set_time(0)
                self._player.play()
            elif state == vlc.State.Error:
                self.errorOccurred.emit("VLC 播放失败")
        except Exception as exc:
            self.errorOccurred.emit(str(exc))

    def _bind_output(self) -> None:
        if self._closed or self._player is None:
            return
        try:
            wid = int(self.video_widget.winId())
            if sys.platform.startswith("win"):
                self._player.set_hwnd(wid)
            elif sys.platform == "darwin":
                self._player.set_nsobject(wid)
            else:
                self._player.set_xwindow(wid)
            self._bound = True
        except Exception as exc:
            self.errorOccurred.emit(str(exc))

    def play(self) -> None:
        if self._closed or self._player is None:
            return
        self.rebind_output()
        self._player.play()

    def pause(self) -> None:
        if self._closed or self._player is None:
            return
        self._player.pause()

    def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._poll_timer.stop()
        player = self._player
        media = self._media
        self._player = None
        self._media = None

        def _release() -> None:
            try:
                if player is not None:
                    player.stop()
            except Exception:
                pass
            try:
                if player is not None:
                    player.release()
            except Exception:
                pass
            try:
                if media is not None:
                    media.release()
            except Exception:
                pass

        threading.Thread(target=_release, daemon=True).start()

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._closed or self._player is None:
            return
        try:
            self._player.audio_set_mute(self._muted)
        except Exception:
            pass

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        if self._closed or self._player is None:
            return
        try:
            self._player.audio_set_volume(0 if self._muted else self._volume)
        except Exception:
            pass

    def set_position(self, position_ms: int) -> None:
        if self._closed or self._player is None:
            return
        try:
            self._player.set_time(max(0, int(position_ms)))
        except Exception:
            pass

    def position(self) -> int:
        if self._closed or self._player is None:
            return 0
        try:
            return max(0, int(self._player.get_time()))
        except Exception:
            return 0

    def duration(self) -> int:
        if self._closed or self._player is None:
            return 0
        try:
            return max(0, int(self._player.get_length()))
        except Exception:
            return 0

    def rebind_output(self) -> None:
        if self._closed:
            return
        if not self.video_widget.isVisible():
            self.video_widget.show()
        self._bind_output()


def create_media_backend(backend_key: str, parent: QWidget, path: Path) -> MediaBackendBase:
    if backend_key == "vlc":
        try:
            return VlcMediaBackend(parent, path)
        except Exception as exc:
            backend = QtMediaBackend(parent, path)
            QTimer.singleShot(0, lambda: backend.errorOccurred.emit(f"VLC 后端不可用，已回退系统模式: {exc}"))
            return backend
    return QtMediaBackend(parent, path)


class OverlayRoundButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, icon_kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._icon_kind = icon_kind
        self._pressed = False
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setToolTipDuration(1500)

    def set_icon_kind(self, icon_kind: str) -> None:
        if self._icon_kind != icon_kind:
            self._icon_kind = icon_kind
            self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pressed and event.button() == Qt.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        self._draw_icon(painter, rect)

    def _draw_icon(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        alpha = 255 if self._pressed else 246 if self._hover else 238
        icon_color = QColor(255, 255, 255, alpha)
        outline = QColor(0, 0, 0, min(180, alpha))
        icon_rect = rect.adjusted(rect.width() * 0.26, rect.height() * 0.22, -rect.width() * 0.26, -rect.height() * 0.22)
        kind = self._icon_kind
        if kind == "play":
            pts = QPolygonF([
                QPointF(icon_rect.left(), icon_rect.top()),
                QPointF(icon_rect.right(), icon_rect.center().y()),
                QPointF(icon_rect.left(), icon_rect.bottom()),
            ])
            play_pen = QPen(outline, 1.1)
            play_pen.setCapStyle(Qt.RoundCap)
            play_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(play_pen)
            painter.setBrush(QBrush(icon_color))
            painter.drawPolygon(pts)
        elif kind == "pause":
            pause_pen = QPen(outline, 1.0)
            pause_pen.setCapStyle(Qt.RoundCap)
            pause_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pause_pen)
            painter.setBrush(QBrush(icon_color))
            bar_w = max(3.0, icon_rect.width() * 0.22)
            gap = bar_w * 0.75
            left_x = icon_rect.center().x() - gap / 2.0 - bar_w
            right_x = icon_rect.center().x() + gap / 2.0
            painter.drawRoundedRect(QRectF(left_x, icon_rect.top(), bar_w, icon_rect.height()), 1.5, 1.5)
            painter.drawRoundedRect(QRectF(right_x, icon_rect.top(), bar_w, icon_rect.height()), 1.5, 1.5)
        elif kind in {"volume", "mute"}:
            self._draw_speaker(painter, icon_rect, kind == "mute", alpha)
        painter.restore()

    def _draw_speaker(self, painter: QPainter, rect: QRectF, muted: bool, alpha: int) -> None:
        outline = QColor(0, 0, 0, min(180, alpha))
        fill = QColor(255, 255, 255, alpha)
        body_w = rect.width() * 0.34
        body = QRectF(rect.left(), rect.top() + rect.height() * 0.28, body_w, rect.height() * 0.44)
        horn = QPolygonF([
            QPointF(body.right(), rect.top() + rect.height() * 0.18),
            QPointF(rect.right() - rect.width() * 0.06, rect.top() + rect.height() * 0.06),
            QPointF(rect.right() - rect.width() * 0.06, rect.bottom() - rect.height() * 0.06),
            QPointF(body.right(), rect.bottom() - rect.height() * 0.18),
        ])
        speaker_pen = QPen(outline, 1.0)
        speaker_pen.setCapStyle(Qt.RoundCap)
        speaker_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(speaker_pen)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(body, 1.5, 1.5)
        painter.drawPolygon(horn)
        shadow_pen = QPen(outline, 2.2)
        shadow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(shadow_pen)
        painter.setBrush(Qt.NoBrush)
        if muted:
            painter.drawLine(QPointF(rect.left() + rect.width() * 0.06, rect.bottom() - rect.height() * 0.08), QPointF(rect.right() - rect.width() * 0.06, rect.top() + rect.height() * 0.08))
        else:
            cx = rect.right() - rect.width() * 0.08
            arc_rect = QRectF(cx - rect.width() * 0.18, rect.top() + rect.height() * 0.18, rect.width() * 0.24, rect.height() * 0.64)
            painter.drawArc(arc_rect, -55 * 16, 110 * 16)
        front_pen = QPen(fill, 1.4)
        front_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(front_pen)
        if muted:
            painter.drawLine(QPointF(rect.left() + rect.width() * 0.06, rect.bottom() - rect.height() * 0.08), QPointF(rect.right() - rect.width() * 0.06, rect.top() + rect.height() * 0.08))
        else:
            painter.drawArc(arc_rect, -55 * 16, 110 * 16)


class OverlayLineSlider(QWidget):
    valueChanged = pyqtSignal(int)
    sliderPressed = pyqtSignal()
    sliderReleased = pyqtSignal()
    sliderMoved = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 0
        self._value = 0
        self._pressed = False
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.PointingHandCursor)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = max(int(maximum), self._minimum)
        self._value = max(self._minimum, min(self._value, self._maximum))
        self.update()

    def setSingleStep(self, _step: int) -> None:
        return

    def setValue(self, value: int) -> None:
        value = max(self._minimum, min(int(value), self._maximum))
        if value == self._value:
            self.update()
            return
        self._value = value
        self.valueChanged.emit(self._value)
        self.update()

    def value(self) -> int:
        return self._value

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        line_y = self.height() / 2.0
        margin = 8.0
        start_x = margin
        end_x = max(start_x + 1.0, self.width() - margin)
        shadow_pen = QPen(QColor(0, 0, 0, 150), 3.2)
        shadow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(shadow_pen)
        painter.drawLine(QPointF(start_x, line_y), QPointF(end_x, line_y))
        pen = QPen(QColor(255, 255, 255, 82), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(start_x, line_y), QPointF(end_x, line_y))
        handle_x = self._value_to_x()
        painter.setPen(QPen(QColor(0, 0, 0, 160), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 242)))
        painter.drawEllipse(QPointF(handle_x, line_y), 5.0, 5.0)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.sliderPressed.emit()
            self._set_value_from_x(event.x(), emit_moved=True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pressed:
            self._set_value_from_x(event.x(), emit_moved=True)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pressed and event.button() == Qt.LeftButton:
            self._set_value_from_x(event.x(), emit_moved=False)
            self._pressed = False
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _value_to_x(self) -> float:
        margin = 8.0
        span = max(1.0, self.width() - margin * 2.0)
        if self._maximum <= self._minimum:
            return margin
        ratio = (self._value - self._minimum) / max(1, self._maximum - self._minimum)
        return margin + span * ratio

    def _set_value_from_x(self, x: int, emit_moved: bool) -> None:
        margin = 8.0
        span = max(1.0, self.width() - margin * 2.0)
        clamped = min(max(float(x), margin), self.width() - margin)
        if self._maximum <= self._minimum:
            value = self._minimum
        else:
            ratio = (clamped - margin) / span
            value = int(round(self._minimum + ratio * (self._maximum - self._minimum)))
        self._value = max(self._minimum, min(value, self._maximum))
        if emit_moved:
            self.sliderMoved.emit(self._value)
        self.valueChanged.emit(self._value)
        self.update()


class VideoTile(QFrame):
    def __init__(self, group: "GroupWindow", item: VideoItem, index: int) -> None:
        super().__init__(group.content)
        self.group = group
        self.item = item
        self.index = index
        self.playback_backend = group.playback_backend
        self._is_paused = False
        self._is_muted = True
        self._volume = 0
        self._duration_ms = 0
        self._seeking = False
        self._drag_start_pos: Optional[QPoint] = None
        self._dragging = False
        self._controls_visible = False
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._hide_controls)

        self.setObjectName("tile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.backend = create_media_backend(self.playback_backend, self, item.path)
        self.video_widget = self.backend.video_widget
        self.video_widget.installEventFilter(self)
        layout.addWidget(self.video_widget, 1)
        actual_backend = getattr(self.backend, "backend_key", self.playback_backend)
        if actual_backend in PLAYBACK_BACKENDS and actual_backend != self.playback_backend:
            self.playback_backend = actual_backend
            self.group.playback_backend = actual_backend

        self.progress_slider = OverlayLineSlider()
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setSingleStep(1000)
        self.progress_slider.sliderPressed.connect(self._on_seek_pressed)
        self.progress_slider.sliderReleased.connect(self._on_seek_released)
        self.progress_slider.sliderMoved.connect(self._on_seek_moved)
        self.play_btn = OverlayRoundButton("pause")
        self.play_btn.setToolTip("暂停 / 播放")
        self.play_btn.clicked.connect(self.toggle_pause)
        self.mute_btn = OverlayRoundButton("mute")
        self.mute_btn.setToolTip("静音 / 取消静音")
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.volume_slider = OverlayLineSlider()
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(0)
        self.volume_slider.setFixedWidth(92)
        self.volume_slider.valueChanged.connect(self.change_volume)
        self.overlay_widgets = [self.progress_slider, self.play_btn, self.mute_btn, self.volume_slider]
        for widget in self.overlay_widgets:
            widget.hide()
            widget.raise_()

        self.backend.errorOccurred.connect(self.on_player_error)
        self.backend.positionChanged.connect(self._sync_position)
        self.backend.durationChanged.connect(self._sync_duration)
        self._pending_restore_position: Optional[int] = None
        self.set_selected(False)

    def on_player_error(self, message: str = "") -> None:
        suffix = f" [播放失败: {message}]" if message else " [播放失败]"
        self.setToolTip(f"{self.item.path.name}{suffix}")

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.backend.rebind_output()
        self._layout_overlay_controls()

    def _layout_overlay_controls(self) -> None:
        compact = self.width() < 210 or self.height() < 180
        ultra_compact = self.width() < 160 or self.height() < 130
        left = 8
        right = max(left, self.width() - 8)
        progress_height = 12 if compact else 14
        progress_width = max(88, min(self.width() - 16, self.width() - 22 if compact else 220))
        progress_x = max(left, (self.width() - progress_width) // 2)
        row_y = max(6, self.height() - (44 if compact else 38))
        progress_y = max(6, row_y - (16 if compact else 18))
        self.progress_slider.setFixedHeight(progress_height)
        global_progress = self.mapToGlobal(QPoint(progress_x, progress_y))
        self.progress_slider.setGeometry(global_progress.x(), global_progress.y(), progress_width, progress_height)

        btn_w = 26
        btn_h = 24
        slider_w = 72 if compact else 92
        gap = 8
        show_volume = not ultra_compact
        total_w = btn_w + gap + btn_w
        if show_volume:
            total_w += gap + slider_w
        start_x = max(left, min((self.width() - total_w) // 2, right - total_w))
        x = start_x
        play_rect = QRect(x, row_y - 2, btn_w, btn_h)
        mute_rect = QRect(x + btn_w + gap, row_y - 2, btn_w, btn_h)
        global_play = self.mapToGlobal(play_rect.topLeft())
        global_mute = self.mapToGlobal(mute_rect.topLeft())
        self.play_btn.setGeometry(global_play.x(), global_play.y(), btn_w, btn_h)
        self.mute_btn.setGeometry(global_mute.x(), global_mute.y(), btn_w, btn_h)
        x += btn_w + gap + btn_w + gap
        if show_volume:
            volume_height = 12 if compact else 14
            global_volume = self.mapToGlobal(QPoint(x, row_y + 4))
            self.volume_slider.setGeometry(global_volume.x(), global_volume.y(), slider_w, volume_height)
        self.volume_slider.setVisible(show_volume and self._controls_visible)

    def _set_controls_visible(self, visible: bool) -> None:
        self._controls_visible = visible
        self.progress_slider.setVisible(visible)
        self.play_btn.setVisible(visible)
        self.mute_btn.setVisible(visible)
        if visible:
            self.play_btn.raise_()
            self.mute_btn.raise_()
        compact = self.width() < 210 or self.height() < 180
        ultra_compact = self.width() < 160 or self.height() < 130
        show_volume = not ultra_compact
        self.volume_slider.setVisible(visible and show_volume)
        if visible:
            self._layout_overlay_controls()

    def enterEvent(self, event) -> None:
        self.hide_timer.stop()
        self._set_controls_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hide_timer.start(2000)
        super().leaveEvent(event)

    def _hide_controls(self) -> None:
        self._set_controls_visible(False)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._dragging = False
        self.group.handle_tile_press(self.index, event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_start_pos is not None:
            if not self._dragging and (event.pos() - self._drag_start_pos).manhattanLength() >= 10:
                self._dragging = True
            if self._dragging:
                center = self.mapTo(self.group.content, event.pos())
                self.group.handle_tile_drag(self.index, center)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self.group.finish_tile_drag(self.index)
        self.group.handle_tile_release(self.index, self._dragging)
        self._drag_start_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.group.show_tile_menu(self.index, QCursor.pos())

    def eventFilter(self, obj, event) -> bool:
        if obj is self.video_widget:
            if event.type() == QEvent.Enter:
                self.enterEvent(event)
                return False
            if event.type() == QEvent.Leave:
                self.leaveEvent(event)
                return False
            if event.type() == QEvent.ContextMenu:
                self.group.show_tile_menu(self.index, event.globalPos())
                return True
            if event.type() == QEvent.MouseButtonPress:
                local_pos = self.mapFromGlobal(event.globalPos())
                self._handle_mouse_press(local_pos, event)
                return True
            if event.type() == QEvent.MouseMove:
                local_pos = self.mapFromGlobal(event.globalPos())
                self._handle_mouse_move(local_pos, event)
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._handle_mouse_release(event)
                return True
        return super().eventFilter(obj, event)

    def _handle_mouse_press(self, local_pos: QPoint, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = local_pos
            self._dragging = False
        self.group.handle_tile_press(self.index, event)

    def _handle_mouse_move(self, local_pos: QPoint, event) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_start_pos is not None:
            if not self._dragging and (local_pos - self._drag_start_pos).manhattanLength() >= 10:
                self._dragging = True
            if self._dragging:
                center = self.mapTo(self.group.content, local_pos)
                self.group.handle_tile_drag(self.index, center)

    def _handle_mouse_release(self, event) -> None:
        if self._dragging:
            self.group.finish_tile_drag(self.index)
        self.group.handle_tile_release(self.index, self._dragging)
        self._drag_start_pos = None
        self._dragging = False

    def toggle_pause(self) -> None:
        self._is_paused = not self._is_paused
        self.play_btn.set_icon_kind("play" if self._is_paused else "pause")
        if self._is_paused:
            self.backend.pause()
        else:
            self.backend.play()

    def toggle_mute(self) -> None:
        self._is_muted = not self._is_muted
        self.backend.set_muted(self._is_muted)
        self.backend.set_volume(0 if self._is_muted else self._volume)
        self._update_volume_icon()

    def change_volume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))
        if not self._is_muted:
            self.backend.set_volume(self._volume)
        self._update_volume_icon()

    def _update_volume_icon(self) -> None:
        self.mute_btn.set_icon_kind("mute" if self._is_muted or self._volume <= 0 else "volume")

    def _sync_position(self, position: int) -> None:
        if self._seeking:
            return
        self.progress_slider.blockSignals(True)
        self.progress_slider.setValue(max(0, int(position)))
        self.progress_slider.blockSignals(False)

    def _sync_duration(self, duration: int) -> None:
        self._duration_ms = max(0, int(duration))
        self.progress_slider.setRange(0, self._duration_ms)
        if self._pending_restore_position is not None and self._duration_ms > 0:
            self.backend.set_position(max(0, min(self._pending_restore_position, self._duration_ms)))
            self._pending_restore_position = None

    def _on_seek_pressed(self) -> None:
        self._seeking = True

    def _on_seek_moved(self, value: int) -> None:
        self._seeking = True
        self.backend.set_position(max(0, int(value)))

    def _on_seek_released(self) -> None:
        self.backend.set_position(max(0, int(self.progress_slider.value())))
        self._seeking = False

    def restart_playback(self) -> None:
        self._is_paused = False
        self.play_btn.set_icon_kind("pause")
        self.backend.restart_playback()

    def snapshot_state(self) -> dict:
        return {
            "position": max(0, int(self.backend.position())),
            "paused": bool(self._is_paused),
            "muted": bool(self._is_muted),
            "volume": int(self._volume),
        }

    def restore_state(self, state: Optional[dict]) -> None:
        if not state:
            return
        self._volume = max(0, min(100, int(state.get("volume", 0))))
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(self._volume)
        self.volume_slider.blockSignals(False)
        self._is_muted = bool(state.get("muted", True))
        self.backend.set_muted(self._is_muted)
        self.backend.set_volume(0 if self._is_muted else self._volume)
        self._update_volume_icon()
        self._is_paused = bool(state.get("paused", False))
        self.play_btn.set_icon_kind("play" if self._is_paused else "pause")
        pos = max(0, int(state.get("position", 0)))
        if self._duration_ms > 0:
            self.backend.set_position(min(pos, self._duration_ms))
        else:
            self._pending_restore_position = pos
        if self._is_paused:
            self.backend.pause()
        else:
            self.backend.play()

    def stop(self) -> None:
        try:
            self.backend.errorOccurred.disconnect(self.on_player_error)
        except Exception:
            pass
        try:
            self.backend.positionChanged.disconnect(self._sync_position)
        except Exception:
            pass
        try:
            self.backend.durationChanged.disconnect(self._sync_duration)
        except Exception:
            pass
        self.backend.stop()
        self.play_btn.hide()
        self.mute_btn.hide()
        self.progress_slider.hide()
        self.volume_slider.hide()
        self.play_btn.close()
        self.mute_btn.close()
        self.progress_slider.close()
        self.volume_slider.close()


class GroupWindow(QWidget):
    def __init__(self, app: "VideoReadApp", group_id: int, name: str, rows: int, smart_layout: bool, layout_algorithm: str = "grid", playback_backend: str = "qt") -> None:
        super().__init__(None)
        self.app = app
        self.group_id = group_id
        self.name = name
        self.rows = max(1, rows)
        self.smart_layout = smart_layout
        self.layout_algorithm = layout_algorithm if layout_algorithm in LAYOUT_ALGOS else "grid"
        self.playback_backend = playback_backend if playback_backend in PLAYBACK_BACKENDS else "qt"
        self.template_path: Optional[Path] = None
        self.items: list[VideoItem] = []
        self.tiles: list[VideoTile] = []
        self.selected_indexes: set[int] = set()
        self._drag_source_index: Optional[int] = None
        self._press_toggle_candidate: Optional[int] = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_from_timer)
        self._screen_fix_timer = QTimer(self)
        self._screen_fix_timer.setSingleShot(True)
        self._screen_fix_timer.timeout.connect(self._force_screen_rebuild)
        self._screen_signal_bound = False
        self._screen_signature: Optional[tuple[str, int, int, int, int, float]] = None

        self.setWindowTitle(name)
        apply_window_icon(self)
        self.setAcceptDrops(True)
        self.resize(1160, 760)
        self.setMinimumSize(560, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.content = QWidget(self)
        self.content.setObjectName("groupContent")
        root.addWidget(self.content, 1)
        self.placeholder = QLabel("拖拽视频到这个窗口，或在主界面中添加视频", self.content)
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setObjectName("placeholder")
        self.placeholder.show()

    def closeEvent(self, event) -> None:
        if self._render_timer.isActive():
            self._render_timer.stop()
        if self._screen_fix_timer.isActive():
            self._screen_fix_timer.stop()
        for tile in self.tiles:
            tile.stop()
            tile.setParent(None)
            tile.deleteLater()
        self.tiles.clear()
        self.app.unregister_group(self.group_id)
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.placeholder.setGeometry(self.content.rect())
        self._bind_screen_events()
        self._maybe_handle_screen_change()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.placeholder.setGeometry(self.content.rect())
        self.schedule_render()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._maybe_handle_screen_change()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths: list[Path] = []
        seen = set()
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() not in VIDEO_EXTS or not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
        self.add_paths(paths)
        self.app.set_active_group(self.group_id)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            self.remove_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def handle_tile_press(self, index: int, event) -> None:
        self.app.set_active_group(self.group_id)
        self._press_toggle_candidate = None
        if event.modifiers() & Qt.ControlModifier:
            if index in self.selected_indexes:
                self.selected_indexes.remove(index)
            else:
                self.selected_indexes.add(index)
        else:
            if index in self.selected_indexes and len(self.selected_indexes) == 1:
                self._press_toggle_candidate = index
            else:
                self.selected_indexes = {index}
        self.refresh_selection()

    def handle_tile_release(self, index: int, dragged: bool) -> None:
        if not dragged and self._press_toggle_candidate == index and index in self.selected_indexes:
            self.selected_indexes.clear()
            self.refresh_selection()
        self._press_toggle_candidate = None

    def handle_tile_drag(self, index: int, point: QPoint) -> None:
        if not (0 <= index < len(self.tiles)):
            return
        if self._drag_source_index is None:
            self._drag_source_index = index
        target_index = self.index_at_point(point)
        if target_index is None or target_index == index or not (0 <= target_index < len(self.tiles)):
            return
        item = self.items.pop(index)
        tile = self.tiles.pop(index)
        self.items.insert(target_index, item)
        self.tiles.insert(target_index, tile)
        if self.selected_indexes:
            moved = set()
            for old_idx in self.selected_indexes:
                if old_idx == index:
                    moved.add(target_index)
                elif index < old_idx <= target_index:
                    moved.add(old_idx - 1)
                elif target_index <= old_idx < index:
                    moved.add(old_idx + 1)
                else:
                    moved.add(old_idx)
            self.selected_indexes = moved
        self.app.mark_dirty()
        self.render(force_rebuild=False)

    def finish_tile_drag(self, _index: int) -> None:
        self._drag_source_index = None
        self.app.refresh_group_list(select_gid=self.group_id)

    def index_at_point(self, point: QPoint) -> Optional[int]:
        for idx, tile in enumerate(self.tiles):
            if tile.geometry().contains(point):
                return idx
        return None

    def show_tile_menu(self, index: int, global_pos: QPoint) -> None:
        if index not in self.selected_indexes:
            self.selected_indexes = {index}
        self.refresh_selection()
        menu = QMenu(self)
        label = "从窗口组移除所选视频" if len(self.selected_indexes) > 1 else "从窗口组移除视频"
        menu.addAction(label, self.remove_selected)
        menu.addAction("全部重新开始播放", self.restart_all_playback)
        menu.addSeparator()
        algo_menu = menu.addMenu("重排算法")
        algo_menu.addAction("使用算法1重排", lambda: self.apply_algorithm("grid"))
        algo_menu.addAction("使用算法2重排", lambda: self.apply_algorithm("justified"))
        menu.addAction("保存为模板", lambda: self.app.save_group_template(self))
        if self.template_path:
            menu.addAction("更新该模板", lambda: self.app.update_linked_template(self))
            menu.addAction("重新加载模板", lambda: self.app.reload_linked_template(self))
        menu.exec_(global_pos)

    def contextMenuEvent(self, event) -> None:
        self.show_window_menu(QCursor.pos())

    def show_window_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        if self.selected_indexes:
            label = "从窗口组移除所选视频" if len(self.selected_indexes) > 1 else "从窗口组移除视频"
            menu.addAction(label, self.remove_selected)
            menu.addSeparator()
        menu.addAction("全部重新开始播放", self.restart_all_playback)
        menu.addSeparator()
        algo_menu = menu.addMenu("重排算法")
        algo_menu.addAction("使用算法1重排", lambda: self.apply_algorithm("grid"))
        algo_menu.addAction("使用算法2重排", lambda: self.apply_algorithm("justified"))
        menu.addAction("保存为模板", lambda: self.app.save_group_template(self))
        if self.template_path:
            menu.addAction("更新该模板", lambda: self.app.update_linked_template(self))
            menu.addAction("重新加载模板", lambda: self.app.reload_linked_template(self))
        menu.exec_(global_pos)

    def refresh_selection(self) -> None:
        for idx, tile in enumerate(self.tiles):
            tile.set_selected(idx in self.selected_indexes)

    def set_layout(self, rows: int, smart_layout: bool, layout_algorithm: str, playback_backend: Optional[str] = None) -> None:
        self.rows = max(1, rows)
        self.smart_layout = smart_layout
        self.layout_algorithm = layout_algorithm if layout_algorithm in LAYOUT_ALGOS else "grid"
        if playback_backend and playback_backend in PLAYBACK_BACKENDS:
            self.playback_backend = playback_backend
        self.app.mark_dirty()
        self.render(force_rebuild=bool(playback_backend))

    def apply_algorithm(self, layout_algorithm: str) -> None:
        self.layout_algorithm = layout_algorithm if layout_algorithm in LAYOUT_ALGOS else self.layout_algorithm
        self.app.mark_dirty()
        self.app.set_active_group(self.group_id)
        self.app.algo_combo.setCurrentText("算法2 (justified)" if self.layout_algorithm == "justified" else "算法1 (smart)")
        self.app.backend_combo.setCurrentText(playback_backend_label(self.playback_backend))
        self.app.refresh_group_list(select_gid=self.group_id)
        self.render()

    def schedule_render(self, delay_ms: int = 120) -> None:
        if self._render_timer.isActive():
            self._render_timer.stop()
        self._render_timer.start(delay_ms)

    def _bind_screen_events(self) -> None:
        handle = self.windowHandle()
        if handle is None or self._screen_signal_bound:
            return
        handle.screenChanged.connect(self._on_screen_changed)
        self._screen_signal_bound = True
        self._screen_signature = self._current_screen_signature()

    def _current_screen_signature(self) -> Optional[tuple[str, int, int, int, int, float]]:
        handle = self.windowHandle()
        screen = handle.screen() if handle is not None else QGuiApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            return None
        geo = screen.availableGeometry()
        return (
            screen.name(),
            geo.x(),
            geo.y(),
            geo.width(),
            geo.height(),
            float(screen.devicePixelRatio()),
        )

    def _maybe_handle_screen_change(self) -> None:
        self._bind_screen_events()
        signature = self._current_screen_signature()
        if signature is None:
            return
        if signature != self._screen_signature:
            self._screen_signature = signature
            self._after_screen_changed()

    def _on_screen_changed(self, _screen) -> None:
        self._screen_signature = self._current_screen_signature()
        self._after_screen_changed()

    def _after_screen_changed(self) -> None:
        self.placeholder.setGeometry(self.content.rect())
        self.content.updateGeometry()
        self.updateGeometry()
        self._render_timer.stop()
        self._screen_fix_timer.stop()
        self.schedule_render(0)
        QTimer.singleShot(120, self._render_from_timer)
        self._screen_fix_timer.start(260)

    def _force_screen_rebuild(self) -> None:
        self.render(force_rebuild=True)

    def _render_from_timer(self) -> None:
        self.render()

    def to_state(self) -> dict:
        return {
            "name": self.name,
            "rows": self.rows,
            "smart_layout": self.smart_layout,
            "layout_algorithm": self.layout_algorithm,
            "playback_backend": self.playback_backend,
            "template_path": str(self.template_path) if self.template_path else "",
            "geometry": geometry_string(self),
            "videos": [str(item.path) for item in self.items],
        }

    def add_paths(self, paths: list[Path]) -> None:
        new_items: list[VideoItem] = []
        for path in paths:
            if path.suffix.lower() not in VIDEO_EXTS or not path.is_file():
                continue
            new_items.append(self.app.probe_video(path))
        if not new_items:
            return
        start_index = len(self.items)
        self.items.extend(new_items)
        for offset, item in enumerate(new_items):
            self.tiles.append(VideoTile(self, item, start_index + offset))
        self.selected_indexes.clear()
        self.app.mark_dirty()
        self.render(force_rebuild=False)
        self.app.refresh_group_list(select_gid=self.group_id)
        self.app.update_status()

    def clear_videos(self) -> None:
        for tile in self.tiles:
            tile.stop()
            tile.setParent(None)
            tile.deleteLater()
        self.items.clear()
        self.tiles.clear()
        self.selected_indexes.clear()
        self._press_toggle_candidate = None
        self._drag_source_index = None

    def remove_selected(self) -> None:
        if not self.selected_indexes:
            return
        for idx in sorted(self.selected_indexes, reverse=True):
            if 0 <= idx < len(self.items):
                self.items.pop(idx)
            if 0 <= idx < len(self.tiles):
                tile = self.tiles.pop(idx)
                tile.stop()
                tile.setParent(None)
                tile.deleteLater()
        self.selected_indexes.clear()
        self._press_toggle_candidate = None
        self.app.mark_dirty()
        self.render(force_rebuild=False)
        self.app.refresh_group_list(select_gid=self.group_id)
        self.app.update_status()

    def restart_all_playback(self) -> None:
        for tile in self.tiles:
            tile.restart_playback()

    def _aspect_ratios(self) -> list[float]:
        return [max(0.05, item.width / max(1, item.height)) for item in self.items]

    def _smart_layout_rects(self, total_w: int, total_h: int) -> list[tuple[int, int, int, int]]:
        count = len(self.items)
        if count <= 0:
            return []

        prefix_ratio = [0.0]
        for item in self.items:
            prefix_ratio.append(prefix_ratio[-1] + max(0.05, item.width / max(1, item.height)))
        total_ratio = prefix_ratio[-1]
        if total_ratio <= 0:
            return []

        ideal_row_height = max(72.0, min(total_h * 0.30, 220.0))
        estimated_rows = max(1, int(round(total_h / max(1.0, ideal_row_height))))
        min_rows = 1
        max_rows = min(count, max(estimated_rows + 10, min(count, 18)))

        best_cost = float("inf")
        best_partitions: list[tuple[int, int]] = []

        for candidate_rows in range(min_rows, max_rows + 1):
            target_row_ratio = max(0.25, total_ratio / candidate_rows)
            dp: list[list[float]] = [[float("inf")] * (count + 1) for _ in range(candidate_rows + 1)]
            prev: list[list[int]] = [[-1] * (count + 1) for _ in range(candidate_rows + 1)]
            dp[0][0] = 0.0

            for row in range(1, candidate_rows + 1):
                remaining_rows = candidate_rows - row
                for end in range(row, count - remaining_rows + 1):
                    start_min = row - 1
                    start_max = end - 1
                    for start in range(start_min, start_max + 1):
                        prior = dp[row - 1][start]
                        if prior == float("inf"):
                            continue
                        row_ratio = prefix_ratio[end] - prefix_ratio[start]
                        items_in_row = end - start
                        variance_penalty = ((row_ratio - target_row_ratio) / max(0.25, target_row_ratio)) ** 2
                        single_penalty = 0.55 if items_in_row == 1 and count > 3 else 0.0
                        overwide_penalty = 0.18 if row_ratio > target_row_ratio * 1.75 else 0.0
                        underwide_penalty = 0.12 if row_ratio < target_row_ratio * 0.55 else 0.0
                        cost = prior + variance_penalty + single_penalty + overwide_penalty + underwide_penalty
                        if cost < dp[row][end]:
                            dp[row][end] = cost
                            prev[row][end] = start

            candidate_cost = dp[candidate_rows][count]
            if candidate_cost == float("inf"):
                continue

            partitions: list[tuple[int, int]] = []
            end = count
            row = candidate_rows
            while row > 0 and end > 0:
                start = prev[row][end]
                if start < 0:
                    partitions = []
                    break
                partitions.append((start, end))
                end = start
                row -= 1
            partitions.reverse()
            if not partitions:
                continue

            row_heights = []
            single_rows = 0
            for start, end in partitions:
                ratio_sum = prefix_ratio[end] - prefix_ratio[start]
                row_heights.append(total_w / max(0.05, ratio_sum))
                if end - start == 1:
                    single_rows += 1

            natural_total_h = sum(row_heights)
            blank_ratio = max(0.0, total_h - natural_total_h) / max(1.0, total_h)
            overflow_ratio = max(0.0, natural_total_h - total_h) / max(1.0, total_h)
            fit_penalty = blank_ratio * 4.6 + overflow_ratio * 8.8
            fit_penalty += abs(natural_total_h - total_h) / max(1.0, total_h) * 1.8
            single_rows_penalty = 0.18 * single_rows
            total_cost = candidate_cost * 0.28 + fit_penalty + single_rows_penalty

            if total_cost < best_cost:
                best_cost = total_cost
                best_partitions = partitions

        partitions = best_partitions
        if not partitions:
            return []

        row_heights: list[float] = []
        for start, end in partitions:
            ratio_sum = prefix_ratio[end] - prefix_ratio[start]
            row_heights.append(total_w / max(0.05, ratio_sum))

        total_height = sum(row_heights)
        if total_height <= 0:
            return []
        scale_y = min(total_h / total_height, 1.0)
        scaled_heights = [max(1, int(h * scale_y)) for h in row_heights]

        rects: list[tuple[int, int, int, int]] = []
        y = 0
        for row_idx, (start, end) in enumerate(partitions):
            row_h = max(1, scaled_heights[row_idx])
            x = 0
            row_items = self.items[start:end]
            widths: list[int] = []
            for item in row_items:
                ratio = item.width / max(1, item.height)
                widths.append(max(1, int(row_h * ratio)))
            row_width = sum(widths)
            if row_width > total_w and row_width > 0:
                shrink = total_w / row_width
                widths = [max(1, int(w * shrink)) for w in widths]
                width_fix = total_w - sum(widths)
                widths[-1] = max(1, widths[-1] + width_fix)

            for item_idx, draw_w in enumerate(widths):
                x0 = x
                x1 = min(total_w, x + max(1, draw_w))
                y1 = min(total_h, y + row_h)
                rects.append((x0, y, x1, y1))
                x = x1
            y += row_h

        while len(rects) < count:
            rects.append((0, 0, total_w, total_h))
        return rects[:count]

    def _justified_layout_rects(self, total_w: int, total_h: int) -> list[tuple[int, int, int, int]]:
        count = len(self.items)
        if count <= 0:
            return []

        ratios = [max(0.05, item.width / max(1, item.height)) for item in self.items]
        prefix_ratio = [0.0]
        for ratio in ratios:
            prefix_ratio.append(prefix_ratio[-1] + ratio)

        min_target_h = max(90.0, min(total_h * 0.12, 180.0))
        max_target_h = max(min_target_h + 20.0, min(total_h * 0.58, 420.0))
        step = 10.0

        best_cost = float("inf")
        best_partitions: list[tuple[int, int]] = []
        best_row_heights: list[float] = []

        target_h = min_target_h
        while target_h <= max_target_h + 0.1:
            dp = [float("inf")] * (count + 1)
            prev = [-1] * (count + 1)
            row_heights = [0.0] * (count + 1)
            dp[0] = 0.0

            for end in range(1, count + 1):
                start_floor = max(0, end - 8)
                for start in range(start_floor, end):
                    if dp[start] == float("inf"):
                        continue
                    ratio_sum = prefix_ratio[end] - prefix_ratio[start]
                    if ratio_sum <= 0:
                        continue
                    height = total_w / ratio_sum
                    items_in_row = end - start
                    cost = dp[start]
                    cost += ((height - target_h) / max(1.0, target_h)) ** 2
                    if items_in_row == 1 and count > 3:
                        cost += 0.45
                    if height < 82:
                        cost += ((82 - height) / 82) * 2.6
                    if height > target_h * 1.9:
                        cost += ((height / max(1.0, target_h)) - 1.9) * 0.9
                    if cost < dp[end]:
                        dp[end] = cost
                        prev[end] = start
                        row_heights[end] = height

            if dp[count] == float("inf"):
                target_h += step
                continue

            partitions: list[tuple[int, int]] = []
            heights_out: list[float] = []
            end = count
            while end > 0:
                start = prev[end]
                if start < 0:
                    partitions = []
                    break
                partitions.append((start, end))
                heights_out.append(row_heights[end])
                end = start
            partitions.reverse()
            heights_out.reverse()
            if not partitions:
                target_h += step
                continue

            total_layout_h = sum(heights_out)
            blank_ratio = max(0.0, total_h - total_layout_h) / max(1.0, total_h)
            overflow_ratio = max(0.0, total_layout_h - total_h) / max(1.0, total_h)
            if overflow_ratio > 0.02:
                target_h += step
                continue
            min_height = min(heights_out) if heights_out else 0.0
            short_penalty = max(0.0, 110.0 - min_height) / 110.0
            total_cost = dp[count] * 0.35 + blank_ratio * 3.8 + overflow_ratio * 2.4 + short_penalty * 1.8

            if total_cost < best_cost:
                best_cost = total_cost
                best_partitions = partitions
                best_row_heights = heights_out

            target_h += step

        if not best_partitions:
            return self._smart_layout_rects(total_w, total_h)

        rects: list[tuple[int, int, int, int]] = []
        y = 0
        for row_idx, (start, end) in enumerate(best_partitions):
            row_h = max(1, int(round(best_row_heights[row_idx])))
            row_ratios = ratios[start:end]
            widths = [max(1, int(round(row_h * ratio))) for ratio in row_ratios]
            width_fix = total_w - sum(widths)
            if widths:
                widths[-1] = max(1, widths[-1] + width_fix)
            x = 0
            for col_idx, draw_w in enumerate(widths):
                x0 = x
                x1 = total_w if col_idx == len(widths) - 1 else x + max(1, draw_w)
                y1 = min(total_h, y + row_h)
                rects.append((x0, y, x1, y1))
                x = x1
            y += row_h

        return rects[:count]

    def _grid_layout_rects(self, total_w: int, total_h: int) -> list[tuple[int, int, int, int]]:
        # Keep the persisted "grid" key for template/session compatibility,
        # but use PicRead-style smart packing so algorithm1 respects aspect
        # ratios and uses space more naturally.
        return self._smart_layout_rects(total_w, total_h)

    def _simple_fallback_rects(self, total_w: int, total_h: int) -> list[tuple[int, int, int, int]]:
        return self._smart_layout_rects(total_w, total_h)

    def _snapshot_tile_states(self) -> dict[str, list[dict]]:
        state_map: dict[str, list[dict]] = {}
        for idx, tile in enumerate(self.tiles):
            if idx >= len(self.items):
                continue
            key = str(self.items[idx].path.resolve())
            state_map.setdefault(key, []).append(tile.snapshot_state())
        return state_map

    def render(self, force_rebuild: bool = False) -> None:
        total_w = max(1, self.content.width())
        total_h = max(1, self.content.height())
        self.placeholder.setGeometry(self.content.rect())
        if not self.items:
            self.placeholder.show()
            if force_rebuild or self.tiles:
                for tile in self.tiles:
                    tile.stop()
                    tile.setParent(None)
                    tile.deleteLater()
                self.tiles = []
            return
        self.placeholder.hide()
        preserved_states = self._snapshot_tile_states() if force_rebuild else {}
        if force_rebuild:
            for tile in self.tiles:
                tile.stop()
                tile.setParent(None)
                tile.deleteLater()
            self.tiles = [VideoTile(self, item, idx) for idx, item in enumerate(self.items)]
        elif len(self.tiles) < len(self.items):
            start_index = len(self.tiles)
            for idx in range(start_index, len(self.items)):
                self.tiles.append(VideoTile(self, self.items[idx], idx))
        elif len(self.tiles) > len(self.items):
            extra = self.tiles[len(self.items):]
            for tile in extra:
                tile.stop()
                tile.setParent(None)
                tile.deleteLater()
            self.tiles = self.tiles[:len(self.items)]
        rects = self._justified_layout_rects(total_w, total_h) if self.layout_algorithm == "justified" else self._grid_layout_rects(total_w, total_h)
        if len(rects) != len(self.items):
            rects = self._simple_fallback_rects(total_w, total_h)
        if len(rects) != len(self.items):
            return
        for idx, tile in enumerate(self.tiles):
            tile.index = idx
            x0, y0, x1, y1 = rects[idx]
            tile.setGeometry(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)))
            if force_rebuild:
                key = str(self.items[idx].path.resolve())
                states = preserved_states.get(key)
                if states:
                    tile.restore_state(states.pop(0))
            tile.show()
        self.refresh_selection()


class VideoReadApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        self.groups: dict[int, GroupWindow] = {}
        self.group_order: list[int] = []
        self.next_group_id = 1
        self.active_group_id: Optional[int] = None
        self.template_entries: list[Path] = []
        self.history_entries: list[Path] = []
        self.dirty = False
        self.last_save_ts = 0.0
        apply_window_icon(self)
        self._apply_dark_theme()
        self._build_ui()
        self._set_initial_geometry()
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(400)
        self.load_session(silent=True)
        self.update_status()

    def _apply_dark_theme(self) -> None:
        self.setWindowTitle(f"VideoRead v{APP_VERSION} - 多窗口组平铺播片")
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor("#1e1e1e"))
        palette.setColor(QPalette.WindowText, QColor("#d4d4d4"))
        palette.setColor(QPalette.Base, QColor("#252526"))
        palette.setColor(QPalette.AlternateBase, QColor("#1b1b1b"))
        palette.setColor(QPalette.Text, QColor("#d4d4d4"))
        palette.setColor(QPalette.Button, QColor("#252526"))
        palette.setColor(QPalette.ButtonText, QColor("#d4d4d4"))
        palette.setColor(QPalette.Highlight, QColor("#264f78"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        QApplication.instance().setPalette(palette)
        self.setStyleSheet(
            "QWidget { background: #1f1f1f; color: #d9d9d9; font-family: 'Microsoft YaHei UI'; font-size: 8pt; }"
            "QLineEdit, QSpinBox, QComboBox, QListWidget { background: #262626; border: 1px solid #4a4a4a; padding: 3px 5px; }"
            "QPushButton, QToolButton { background: #242424; border: 1px solid #6a6a6a; padding: 4px 9px; min-height: 24px; color: #f3f3f3; }"
            "QPushButton:hover, QToolButton:hover { background: #303030; color: #ffffff; }"
            "QPushButton:pressed, QToolButton:pressed { background: #1d1d1d; }"
            "QTabWidget::pane { border: 1px solid #6e6e6e; top: -1px; }"
            "QTabBar::tab { background: #242424; border: 1px solid #6e6e6e; padding: 4px 11px; margin-right: 2px; }"
            "QTabBar::tab:selected { background: #2f2f2f; color: #ffffff; }"
            "QMenu { background: #202020; color: #f1f1f1; border: 1px solid #666666; }"
            "QMenu::item { padding: 6px 20px 6px 14px; }"
            "QMenu::item:selected { background: #264f78; color: #ffffff; }"
            "QLabel#title { font-size: 15pt; font-weight: 700; color: #f1f1f1; }"
            "QLabel#placeholder { color: #8f98a0; font-size: 11pt; }"
            "QWidget#groupContent { background: #101010; }"
            "QFrame#tile { background: #141414; border: 2px solid #2c2c2c; }"
            "QFrame#tile[selected=\"true\"] { border: 2px solid #f7c948; }"

        )

    def _set_initial_geometry(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        width = min(max(760, int(screen.width() * 0.44)), max(700, screen.width() - 20))
        height = min(max(520, int(screen.height() * 0.50)), max(500, screen.height() - 20))
        x = screen.x() + max(6, (screen.width() - width) // 2)
        y = screen.y() + max(6, (screen.height() - height) // 2)
        self.setGeometry(x, y, width, height)
        self.setMinimumSize(720, 520)

    def _build_ui(self) -> None:
        root = QWidget(self)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        title = QLabel(f"VideoRead v{APP_VERSION} | 多窗口组平铺播片", root)
        title.setObjectName("title")
        outer.addWidget(title)

        tabs = QTabWidget(root)
        outer.addWidget(tabs, 1)
        self.tabs = tabs

        group_tab = QWidget()
        group_layout = QVBoxLayout(group_tab)
        control = QHBoxLayout()
        self.group_name_edit = QLineEdit("视频窗口组")
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 12)
        self.rows_spin.setFixedWidth(64)
        self.rows_spin.setValue(2)
        self.smart_check = QCheckBox("智能排版")
        self.smart_check.setChecked(True)
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(["算法1 (smart)", "算法2 (justified)"])
        self.algo_combo.setFixedWidth(148)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems([playback_backend_label("qt"), playback_backend_label("vlc")])
        self.backend_combo.setFixedWidth(166)
        create_btn = QPushButton("创建窗口组")
        create_btn.clicked.connect(self.create_group)
        control.addWidget(QLabel("窗口组名:"))
        control.addWidget(self.group_name_edit, 1)
        control.addWidget(QLabel("行数:"))
        control.addWidget(self.rows_spin)
        control.addWidget(self.smart_check)
        control.addWidget(QLabel("算法:"))
        control.addWidget(self.algo_combo)
        control.addWidget(QLabel("播放后端:"))
        control.addWidget(self.backend_combo)
        control.addWidget(create_btn)
        group_layout.addLayout(control)

        self.group_list = QListWidget()
        self.group_list.currentRowChanged.connect(lambda _row: self.on_group_selected())
        group_layout.addWidget(self.group_list, 1)

        btns = QHBoxLayout()
        for text, handler in (
            ("添加视频", self.add_videos),
            ("应用布局", self.apply_layout),
            ("保存为模板", self.save_group_template),
            ("保存会话", self.save_session_snapshot),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            btns.addWidget(button)
        btns.addStretch(1)
        close_btn = QPushButton("关闭窗口组")
        close_btn.clicked.connect(self.close_group)
        btns.addWidget(close_btn)
        group_layout.addLayout(btns)
        tabs.addTab(group_tab, "窗口组")

        template_tab = QWidget()
        template_layout = QVBoxLayout(template_tab)
        tpl_btns = QHBoxLayout()
        for text, handler in (
            ("刷新模板库", self.refresh_template_library),
            ("打开模板", self.load_group_template),
            ("更新该模板", self.update_linked_template),
            ("重新加载模板", self.reload_linked_template),
            ("删除模板", self.delete_selected_template),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            tpl_btns.addWidget(button)
        tpl_btns.addStretch(1)
        template_layout.addLayout(tpl_btns)
        self.template_list = QListWidget()
        self.template_list.itemDoubleClicked.connect(lambda _item: self.load_group_template())
        template_layout.addWidget(self.template_list, 1)
        tabs.addTab(template_tab, "模板库")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        hist_btns = QHBoxLayout()
        refresh_history = QPushButton("刷新历史")
        refresh_history.clicked.connect(self.refresh_history_library)
        open_history = QPushButton("打开所选历史")
        open_history.clicked.connect(self.open_selected_history)
        hist_btns.addWidget(refresh_history)
        hist_btns.addWidget(open_history)
        hist_btns.addStretch(1)
        history_layout.addLayout(hist_btns)
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(lambda _item: self.open_selected_history())
        history_layout.addWidget(self.history_list, 1)
        tabs.addTab(history_tab, "历史记录")

        self.status_label = QLabel("就绪")
        outer.addWidget(self.status_label)
        self.setCentralWidget(root)
        self.refresh_template_library()
        self.refresh_history_library()

    def current_layout_algo(self) -> str:
        return "justified" if "justified" in self.algo_combo.currentText() else "grid"

    def current_playback_backend(self) -> str:
        return playback_backend_from_label(self.backend_combo.currentText())

    def mark_dirty(self) -> None:
        self.dirty = True

    def probe_video(self, path: Path) -> VideoItem:
        item = VideoItem(path=path)
        width, height, rotate = ffprobe_video_info(path)
        if rotate in (90, 270):
            width, height = height, width
        if width > 0 and height > 0:
            item.width = width
            item.height = height
        if av is None:
            return item
        try:
            with av.open(str(path)) as container:
                stream = container.streams.video[0]
                if item.width <= 1 or item.height <= 1:
                    width = int(getattr(stream, "width", 0) or getattr(stream.codec_context, "width", 0) or 0)
                    height = int(getattr(stream, "height", 0) or getattr(stream.codec_context, "height", 0) or 0)
                    rotate_raw = str(getattr(stream, "metadata", {}).get("rotate", "0") or "0").strip()
                    try:
                        rotate = int(float(rotate_raw)) % 360
                    except Exception:
                        rotate = 0
                    if width <= 0 or height <= 0:
                        try:
                            first_frame = next(container.decode(video=0))
                            width = int(getattr(first_frame, "width", width) or width)
                            height = int(getattr(first_frame, "height", height) or height)
                        except Exception:
                            pass
                    if rotate in (90, 270):
                        width, height = height, width
                    item.width = max(1, width or item.width)
                    item.height = max(1, height or item.height)
                if stream.duration is not None and stream.time_base is not None:
                    item.duration_ms = max(0, int(float(stream.duration * stream.time_base) * 1000))
                elif container.duration:
                    item.duration_ms = max(0, int(container.duration / 1000))
        except Exception:
            pass
        return item

    def collect_video_paths(self, paths) -> list[Path]:
        result: list[Path] = []
        seen = set()
        for raw in paths:
            path = Path(str(raw))
            if path.suffix.lower() not in VIDEO_EXTS or not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    def create_group(self) -> None:
        gid = self.next_group_id
        self.next_group_id += 1
        name = self.group_name_edit.text().strip() or f"视频窗口组{gid}"
        backend = self.resolve_backend_choice(self.current_playback_backend(), parent=self, fallback_to_qt=False)
        if backend is None:
            self.next_group_id -= 1
            return
        group = GroupWindow(self, gid, name, int(self.rows_spin.value()), self.smart_check.isChecked(), self.current_layout_algo(), playback_backend=backend)
        self.groups[gid] = group
        self.group_order.append(gid)
        group.show()
        group.raise_()
        group.activateWindow()
        self.mark_dirty()
        self.refresh_group_list(select_gid=gid)
        self.update_status()

    def refresh_group_list(self, select_gid: Optional[int] = None) -> None:
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for gid in self.group_order:
            group = self.groups.get(gid)
            if group is None:
                continue
            algo = f" | algo={LAYOUT_ALGOS.get(group.layout_algorithm, '算法1')}" if group.smart_layout else ""
            backend = f" | {group.playback_backend.upper()}"
            item = QListWidgetItem(f"{group.name} | rows={group.rows} | {len(group.items)} videos{algo}{backend}")
            item.setData(Qt.UserRole, gid)
            self.group_list.addItem(item)
            if select_gid == gid or (select_gid is None and self.active_group_id == gid):
                self.group_list.setCurrentItem(item)
        self.group_list.blockSignals(False)
        if self.group_list.currentRow() >= 0:
            self.on_group_selected()

    def dialog_parent(self, target_group: Optional[GroupWindow] = None) -> QWidget:
        if target_group is not None:
            try:
                if target_group.isVisible():
                    return target_group
            except Exception:
                pass
        return self

    def prepare_dialog(self, dialog: QDialog, parent: QWidget) -> None:
        dialog.setParent(parent, dialog.windowFlags())
        dialog.setWindowModality(Qt.WindowModal)
        QTimer.singleShot(0, dialog.raise_)
        QTimer.singleShot(0, dialog.activateWindow)

    def show_info(self, parent: QWidget, title: str, text: str) -> None:
        QMessageBox.information(parent, title, text)

    def show_error(self, parent: QWidget, title: str, text: str) -> None:
        QMessageBox.critical(parent, title, text)

    def ask_yes_no(self, parent: QWidget, title: str, text: str) -> bool:
        return QMessageBox.question(parent, title, text) == QMessageBox.Yes

    def resolve_backend_choice(self, backend: str, parent: Optional[QWidget] = None, fallback_to_qt: bool = True) -> Optional[str]:
        backend = backend if backend in PLAYBACK_BACKENDS else "qt"
        if backend != "vlc":
            return "qt"
        if is_vlc_runtime_available():
            return "vlc"
        target_parent = parent or self
        if fallback_to_qt:
            self.show_info(target_parent, "提示", "当前未检测到可用的 VLC 运行库，将自动回退到系统模式。")
            return "qt"
        self.show_info(target_parent, "提示", "当前未检测到可用的 VLC 运行库，请先安装 VLC 或切换回系统模式。")
        return None

    def selected_group(self) -> Optional[GroupWindow]:
        item = self.group_list.currentItem()
        if item is None:
            return None
        gid = item.data(Qt.UserRole)
        return self.groups.get(int(gid)) if gid is not None else None

    def set_active_group(self, gid: int) -> None:
        if gid not in self.groups:
            return
        self.active_group_id = gid
        for row in range(self.group_list.count()):
            item = self.group_list.item(row)
            if item.data(Qt.UserRole) == gid:
                self.group_list.setCurrentRow(row)
                break
        self.on_group_selected()

    def on_group_selected(self) -> None:
        group = self.selected_group()
        if group is None:
            return
        self.active_group_id = group.group_id
        self.group_name_edit.setText(group.name)
        self.rows_spin.setValue(group.rows)
        self.smart_check.setChecked(group.smart_layout)
        self.algo_combo.setCurrentText("算法2 (justified)" if group.layout_algorithm == "justified" else "算法1 (smart)")
        self.backend_combo.setCurrentText(playback_backend_label(group.playback_backend))

    def add_videos(self) -> None:
        group = self.selected_group()
        if group is None:
            QMessageBox.information(self, "提示", "请先创建并选中一个窗口组。")
            return
        picked, _ = QFileDialog.getOpenFileNames(self, "选择视频", str(APP_DIR), "视频 (*.mp4 *.mkv *.avi *.mov *.wmv *.webm *.m4v *.ts *.flv);;所有文件 (*.*)")
        paths = self.collect_video_paths(picked)
        if paths:
            group.add_paths(paths)

    def apply_layout(self) -> None:
        group = self.selected_group()
        if group is None:
            QMessageBox.information(self, "提示", "请先在列表里选择一个窗口组。")
            return
        group.name = self.group_name_edit.text().strip() or group.name
        group.setWindowTitle(group.name)
        requested_backend = self.resolve_backend_choice(self.current_playback_backend(), parent=group, fallback_to_qt=False)
        if requested_backend is None:
            self.backend_combo.setCurrentText(playback_backend_label(group.playback_backend))
            return
        rebuild_backend = requested_backend if requested_backend != group.playback_backend else None
        group.set_layout(int(self.rows_spin.value()), self.smart_check.isChecked(), self.current_layout_algo(), playback_backend=rebuild_backend)
        self.mark_dirty()
        self.refresh_group_list(select_gid=group.group_id)

    def close_group(self) -> None:
        group = self.selected_group()
        if group is not None:
            group.close()

    def unregister_group(self, gid: int) -> None:
        self.groups.pop(gid, None)
        if gid in self.group_order:
            self.group_order.remove(gid)
        if self.active_group_id == gid:
            self.active_group_id = None
        self.mark_dirty()
        self.refresh_group_list()
        self.update_status()

    def save_group_template(self, target_group: Optional[GroupWindow] = None) -> None:
        group = target_group or self.selected_group()
        parent = self.dialog_parent(group)
        if group is None:
            self.show_info(parent, "提示", "请先选择一个窗口组。")
            return
        current_category = ""
        if group.template_path and group.template_path.exists():
            try:
                current_category = str(json.loads(group.template_path.read_text(encoding="utf-8")).get("category", "")).strip()
            except Exception:
                current_category = ""
        dialog = TemplateInfoDialog(parent, group.name, current_category)
        self.prepare_dialog(dialog, parent)
        if dialog.exec_() != QDialog.Accepted:
            return
        name, category = dialog.values()
        if not name:
            return
        payload = group.to_state()
        payload["template_name"] = name
        payload["category"] = category
        path = TEMPLATE_DIR / f"{sanitize_template_name(name)}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        group.template_path = path
        self.refresh_template_library()

    def update_linked_template(self, target_group: Optional[GroupWindow] = None) -> None:
        group = target_group or self.selected_group()
        parent = self.dialog_parent(group)
        if group is None:
            self.show_info(parent, "提示", "请先选择一个窗口组。")
            return
        if not group.template_path:
            self.show_info(parent, "提示", "当前组没有关联模板，请先保存为模板。")
            return
        data = group.to_state()
        old = {}
        try:
            if group.template_path.exists():
                old = json.loads(group.template_path.read_text(encoding="utf-8"))
        except Exception:
            old = {}
        data["template_name"] = str(old.get("template_name", group.name)).strip() or group.name
        data["category"] = str(old.get("category", "")).strip()
        try:
            group.template_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.refresh_template_library()
        except Exception as exc:
            self.show_error(parent, "更新失败", str(exc))

    def reload_linked_template(self, target_group: Optional[GroupWindow] = None) -> None:
        group = target_group or self.selected_group()
        parent = self.dialog_parent(group)
        if group is None:
            self.show_info(parent, "提示", "请先选择一个窗口组。")
            return
        if not group.template_path or not group.template_path.exists():
            self.show_info(parent, "提示", "当前组没有可用的关联模板。")
            return
        data = json.loads(group.template_path.read_text(encoding="utf-8"))
        group.name = str(data.get("template_name", data.get("name", group.name))).strip() or group.name
        group.setWindowTitle(group.name)
        group.rows = max(1, int(data.get("rows", group.rows)))
        group.smart_layout = bool(data.get("smart_layout", group.smart_layout))
        group.layout_algorithm = str(data.get("layout_algorithm", group.layout_algorithm)).strip() or group.layout_algorithm
        group.clear_videos()
        video_paths = [Path(p) for p in data.get("videos", []) if Path(p).is_file()]
        group.add_paths(video_paths)
        geo = str(data.get("geometry", "")).strip()
        if geo:
            apply_geometry(group, geo)
        self.refresh_group_list(select_gid=group.group_id)

    def refresh_template_library(self) -> None:
        self.template_list.clear()
        self.template_entries = []
        for path in sorted(TEMPLATE_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                name = str(data.get("template_name", path.stem)).strip() or path.stem
                count = len(data.get("videos", []))
                algo = LAYOUT_ALGOS.get(str(data.get("layout_algorithm", "grid")), "算法1")
                backend = str(data.get("playback_backend", "qt")).strip() or "qt"
                category = str(data.get("category", "")).strip()
                extra = f" | {category}" if category else ""
                self.template_list.addItem(f"{name} | {count} videos | {algo} | {backend.upper()}{extra}")
                self.template_entries.append(path)
            except Exception:
                continue

    def selected_template_path(self) -> Optional[Path]:
        row = self.template_list.currentRow()
        if 0 <= row < len(self.template_entries):
            return self.template_entries[row]
        return None

    def load_group_template(self) -> None:
        path = self.selected_template_path()
        if path is None:
            self.show_info(self, "提示", "请先在模板库里选择一个模板。")
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        gid = self.next_group_id
        self.next_group_id += 1
        name = str(data.get("template_name", path.stem)).strip() or path.stem
        backend = self.resolve_backend_choice(self.current_playback_backend(), parent=self, fallback_to_qt=False)
        if backend is None:
            self.next_group_id -= 1
            return
        group = GroupWindow(self, gid, name, max(1, int(data.get("rows", 2))), bool(data.get("smart_layout", True)), str(data.get("layout_algorithm", "grid")).strip() or "grid", playback_backend=backend)
        group.template_path = path
        self.groups[gid] = group
        self.group_order.append(gid)
        geo = str(data.get("geometry", "")).strip()
        if geo:
            apply_geometry(group, geo)
        group.show()
        group.raise_()
        group.activateWindow()
        group.add_paths([Path(p) for p in data.get("videos", []) if Path(p).is_file()])
        self.mark_dirty()
        self.refresh_group_list(select_gid=gid)
        self.update_status()

    def delete_selected_template(self) -> None:
        path = self.selected_template_path()
        if path is None:
            self.show_info(self, "提示", "请先在模板库里选择一个模板。")
            return
        if not self.ask_yes_no(self, "删除模板", f"确定删除模板 {path.stem} 吗？\n\n不会删除原始视频文件。"):
            return
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            self.show_error(self, "删除失败", str(exc))
            return
        self.refresh_template_library()

    def session_payload(self) -> dict:
        return {
            "version": 1,
            "app_version": APP_VERSION,
            "saved_at": int(time.time()),
            "groups": [self.groups[gid].to_state() for gid in self.group_order if gid in self.groups],
        }

    def write_history_snapshot(self, payload: dict) -> None:
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        path = HISTORY_DIR / f"session_{stamp}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_session(self, silent: bool = False, snapshot: bool = False) -> None:
        payload = self.session_payload()
        SESSION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if snapshot:
            self.write_history_snapshot(payload)
        self.refresh_history_library()
        self.dirty = False
        self.last_save_ts = time.time()
        if not silent:
            QMessageBox.information(self, "完成", "会话已保存。")

    def save_session_snapshot(self) -> None:
        self.save_session(silent=False, snapshot=True)

    def refresh_history_library(self) -> None:
        self.history_list.clear()
        self.history_entries = []
        if SESSION_FILE.exists():
            self.history_list.addItem("session.json")
            self.history_entries.append(SESSION_FILE)
        for path in sorted(HISTORY_DIR.glob("session_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            self.history_list.addItem(path.name)
            self.history_entries.append(path)

    def open_selected_history(self) -> None:
        row = self.history_list.currentRow()
        if not (0 <= row < len(self.history_entries)):
            QMessageBox.information(self, "提示", "请先选择一条历史记录。")
            return
        path = self.history_entries[row]
        if self.groups:
            reply = QMessageBox.question(self, "恢复会话", "恢复会话会替换当前窗口组，是否继续？")
            if reply != QMessageBox.Yes:
                return
        self.load_session(path=path, silent=False)

    def close_all_groups(self) -> None:
        for gid in list(self.group_order):
            group = self.groups.get(gid)
            if group is not None:
                group.close()
        self.groups.clear()
        self.group_order.clear()
        self.active_group_id = None
        self.refresh_group_list()

    def load_session(self, path: Optional[Path] = None, silent: bool = True) -> None:
        source = path or SESSION_FILE
        if not source.exists():
            return
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "读取失败", str(exc))
            return
        self.close_all_groups()
        for item in payload.get("groups", []):
            gid = self.next_group_id
            self.next_group_id += 1
            name = str(item.get("name", f"视频窗口组{gid}")).strip() or f"视频窗口组{gid}"
            backend = self.resolve_backend_choice(str(item.get("playback_backend", "qt")).strip() or "qt", parent=self, fallback_to_qt=True) or "qt"
            group = GroupWindow(self, gid, name, max(1, int(item.get("rows", 2))), bool(item.get("smart_layout", True)), str(item.get("layout_algorithm", "grid")).strip() or "grid", playback_backend=backend)
            template_path = str(item.get("template_path", "")).strip()
            if template_path:
                group.template_path = Path(template_path)
            geo = str(item.get("geometry", "")).strip()
            if geo:
                apply_geometry(group, geo)
            self.groups[gid] = group
            self.group_order.append(gid)
            group.show()
            group.add_paths([Path(p) for p in item.get("videos", []) if Path(p).is_file()])
        self.dirty = False
        self.refresh_group_list()
        self.update_status()
        if not silent:
            QMessageBox.information(self, "完成", "会话恢复完成。")

    def update_status(self) -> None:
        total_groups = len(self.groups)
        total_videos = sum(len(group.items) for group in self.groups.values())
        known_ratio = sum(1 for group in self.groups.values() for item in group.items if item.width > 1 and item.height > 1)
        qt_groups = sum(1 for group in self.groups.values() if group.playback_backend == "qt")
        vlc_groups = sum(1 for group in self.groups.values() if group.playback_backend == "vlc")
        self.status_label.setText(
            f"播放后端: Qt={qt_groups} / VLC={vlc_groups} | 拖拽:开 | 窗口组:{total_groups} | 视频:{total_videos} | 已识别比例:{known_ratio}"
        )

    def tick(self) -> None:
        self.update_status()
        if self.dirty and time.time() - self.last_save_ts > 5:
            self.save_session(silent=True, snapshot=False)

    def closeEvent(self, event) -> None:
        try:
            self.save_session(silent=True, snapshot=True)
        except Exception:
            pass
        self.close_all_groups()
        super().closeEvent(event)


def main() -> None:
    ensure_dirs()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = VideoReadApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
