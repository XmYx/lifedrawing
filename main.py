"""
Live Drawing Countdown + Announcer (PyQt6, single-file app) – Full Revision

Features:
- Pose list builder (minutes + seconds per pose)
- Start session
- Auto-advance checkbox (can disable for single manual runs)
- Manual "Next Pose" button
- Large white countdown over black background
- Announcer sound cues:
    session_start, pose_start, 5 min, 1 min, 30 sec, over
- Sound recorder (uses SYSTEM DEFAULT input device – macOS friendly)
- Save / Load full soundbank (.soundbank zip with manifest + audio files)
- Uses signals & slots cleanly (TimerEngine emits signals, no GUI blocking)

Recommended: Record WAV files for best compatibility.
"""

import json
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List

from PyQt6.QtCore import Qt, QTimer, QUrl, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFileDialog,
    QGroupBox,
    QComboBox,
    QCheckBox,
)

from PyQt6.QtMultimedia import (
    QSoundEffect,
    QAudioInput,
    QMediaRecorder,
    QMediaCaptureSession,
    QMediaFormat,
    QMediaDevices,
)

APP_NAME = "Live Drawing Timer + Announcer"
SOUNDBANK_EXT = "soundbank"

CUES = [
    ("session_start", "Session Start"),
    ("pose_start", "Pose Start"),
    ("five_min", "5 Minutes Remaining"),
    ("one_min", "1 Minute Remaining"),
    ("thirty_sec", "30 Seconds Remaining"),
    ("over", "Over"),
]


# -------------------- Utilities --------------------

def seconds_to_hhmmss(total: int) -> str:
    if total < 0:
        total = 0
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:01d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


@dataclass
class Pose:
    seconds: int

    def label(self) -> str:
        return seconds_to_hhmmss(self.seconds)


# -------------------- SoundBank --------------------

class SoundBank(QObject):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.cue_files: Dict[str, Optional[Path]] = {k: None for k, _ in CUES}
        self._effects: Dict[str, QSoundEffect] = {}

        for cue_key, _ in CUES:
            eff = QSoundEffect()
            eff.setLoopCount(1)
            eff.setVolume(0.9)
            self._effects[cue_key] = eff

    def set_cue_file(self, cue_key: str, path: Optional[Path]) -> None:
        self.cue_files[cue_key] = path
        eff = self._effects.get(cue_key)
        if eff:
            if path and path.exists():
                eff.setSource(QUrl.fromLocalFile(str(path)))
            else:
                eff.setSource(QUrl())

    def get_cue_file(self, cue_key: str) -> Optional[Path]:
        return self.cue_files.get(cue_key)

    def play(self, cue_key: str) -> None:
        eff = self._effects.get(cue_key)
        p = self.cue_files.get(cue_key)
        if eff and p and p.exists():
            eff.stop()
            eff.play()

    def export_soundbank(self, out_path: Path) -> None:
        out_path = out_path.with_suffix(f".{SOUNDBANK_EXT}")
        manifest = {"version": 1, "cues": {}}

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for cue_key, _ in CUES:
                src = self.cue_files.get(cue_key)
                if src and src.exists():
                    arc_name = f"{cue_key}{src.suffix.lower()}"
                    zf.write(src, arcname=arc_name)
                    manifest["cues"][cue_key] = arc_name
                else:
                    manifest["cues"][cue_key] = None

            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    def import_soundbank(self, in_path: Path) -> None:
        with zipfile.ZipFile(in_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            cues = manifest.get("cues", {})

            stamp = time.strftime("%Y%m%d_%H%M%S")
            target_dir = self.base_dir / f"soundbank_{stamp}"
            target_dir.mkdir(parents=True, exist_ok=True)

            for cue_key, _ in CUES:
                arc_name = cues.get(cue_key)
                if arc_name and arc_name in zf.namelist():
                    dest = target_dir / Path(arc_name).name
                    with zf.open(arc_name, "r") as src_f, open(dest, "wb") as dst_f:
                        dst_f.write(src_f.read())
                    self.set_cue_file(cue_key, dest)


# -------------------- Recorder --------------------

class RecorderController(QWidget):
    def __init__(self, soundbank: SoundBank):
        super().__init__()
        self.soundbank = soundbank

        self.capture_session = QMediaCaptureSession()
        self.recorder = QMediaRecorder()
        self.capture_session.setRecorder(self.recorder)

        # SYSTEM DEFAULT input device (macOS safe)
        default_device = QMediaDevices.defaultAudioInput()
        self.audio_input = QAudioInput(default_device)
        self.capture_session.setAudioInput(self.audio_input)

        self.recorder.errorOccurred.connect(self._on_error)

        self.cue_combo = QComboBox()
        for cue_key, cue_name in CUES:
            self.cue_combo.addItem(cue_name, cue_key)

        self.btn_record = QPushButton("● Record")
        self.btn_stop = QPushButton("■ Stop")
        self.btn_play = QPushButton("▶ Play Cue")

        self.status = QLabel("Using system default microphone.")
        self.status.setWordWrap(True)

        self.btn_stop.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.cue_combo)

        row = QHBoxLayout()
        row.addWidget(self.btn_record)
        row.addWidget(self.btn_stop)
        row.addWidget(self.btn_play)
        layout.addLayout(row)

        layout.addWidget(self.status)

        self.btn_record.clicked.connect(self.start_recording)
        self.btn_stop.clicked.connect(self.stop_recording)
        self.btn_play.clicked.connect(self.play_selected)

    def start_recording(self):
        cue_key = self.cue_combo.currentData()
        out_path = self.soundbank.base_dir / f"{cue_key}_{int(time.time())}.wav"

        fmt = QMediaFormat()
        fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
        self.recorder.setMediaFormat(fmt)

        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(out_path)))
        self.recorder.record()

        self.btn_record.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.status.setText("Recording...")

    def stop_recording(self):
        self.recorder.stop()
        self.btn_record.setEnabled(True)
        self.btn_stop.setEnabled(False)

        cue_key = self.cue_combo.currentData()
        out_url = self.recorder.outputLocation()
        out_path = Path(out_url.toLocalFile())

        if out_path.exists():
            self.soundbank.set_cue_file(cue_key, out_path)
            self.status.setText(f"Saved: {out_path.name}")
        else:
            self.status.setText("Recording failed.")

    def play_selected(self):
        cue_key = self.cue_combo.currentData()
        self.soundbank.play(cue_key)

    def _on_error(self, err, err_str):
        self.status.setText(f"Recorder error: {err_str}")


# -------------------- Timer Engine --------------------

class TimerEngine(QObject):
    tick_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.remaining = 0
        self.running = False
        self._last = 0
        self.timer = QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._tick)

    def start(self, seconds: int):
        self.remaining = seconds
        self.running = True
        self._last = time.monotonic()
        self.timer.start()
        self.tick_signal.emit(self.remaining)

    def stop(self):
        self.running = False
        self.timer.stop()

    def _tick(self):
        if not self.running:
            return
        now = time.monotonic()
        dt = int(now - self._last)
        if dt <= 0:
            return
        self._last = now
        self.remaining -= dt
        self.tick_signal.emit(self.remaining)
        if self.remaining <= 0:
            self.running = False
            self.timer.stop()
            self.finished_signal.emit()


# -------------------- Main Window --------------------

class TimerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(QSize(1100, 650))

        self.data_dir = Path.home() / ".live_drawing_timer"
        self.soundbank = SoundBank(self.data_dir / "sounds")

        self.engine = TimerEngine()
        self.engine.tick_signal.connect(self.update_display)
        self.engine.finished_signal.connect(self.on_pose_finished)

        self.poses: List[Pose] = []
        self.current_index = -1

        # Display
        self.display = QLabel("00:00")
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display.setStyleSheet("background:black;color:white;")
        font = QFont()
        font.setPointSize(96)
        font.setBold(True)
        self.display.setFont(font)

        self.pose_info = QLabel("Idle")
        self.pose_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pose_info.setStyleSheet("background:black;color:white;")

        # Pose builder
        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 180)
        self.spin_min.setValue(5)

        self.spin_sec = QSpinBox()
        self.spin_sec.setRange(0, 59)

        self.btn_add = QPushButton("Add Pose")
        self.btn_add.clicked.connect(self.add_pose)

        self.pose_list = QListWidget()

        # Session controls
        self.btn_start = QPushButton("Start")
        self.btn_next = QPushButton("Next Pose")
        self.chk_auto_advance = QCheckBox("Auto-Advance")
        self.chk_auto_advance.setChecked(True)

        self.btn_start.clicked.connect(self.start_session)
        self.btn_next.clicked.connect(self.next_pose)

        # Soundbank buttons
        self.btn_save_bank = QPushButton("Save Soundbank")
        self.btn_load_bank = QPushButton("Load Soundbank")

        self.btn_save_bank.clicked.connect(self.save_soundbank)
        self.btn_load_bank.clicked.connect(self.load_soundbank)

        # Recorder
        self.recorder = RecorderController(self.soundbank)

        # Layout
        left = QVBoxLayout()
        left.addWidget(QLabel("Minutes"))
        left.addWidget(self.spin_min)
        left.addWidget(QLabel("Seconds"))
        left.addWidget(self.spin_sec)
        left.addWidget(self.btn_add)
        left.addWidget(self.pose_list)
        left.addWidget(self.btn_start)
        left.addWidget(self.btn_next)
        left.addWidget(self.chk_auto_advance)
        left.addWidget(self.btn_save_bank)
        left.addWidget(self.btn_load_bank)
        left.addWidget(self.recorder)

        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(self.display)
        right.addWidget(self.pose_info)

        right_widget = QWidget()
        right_widget.setLayout(right)

        root = QHBoxLayout()
        root.addWidget(left_widget)
        root.addWidget(right_widget)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

    # -------- Pose management --------

    def add_pose(self):
        total = self.spin_min.value() * 60 + self.spin_sec.value()
        if total <= 0:
            return
        self.poses.append(Pose(total))
        self.pose_list.addItem(seconds_to_hhmmss(total))

    def start_session(self):
        if not self.poses:
            return
        self.current_index = 0
        self.soundbank.play("session_start")
        self.start_pose()

    def start_pose(self):
        pose = self.poses[self.current_index]
        self.pose_info.setText(f"Pose {self.current_index + 1}")
        self.soundbank.play("pose_start")
        self.engine.start(pose.seconds)

    def next_pose(self):
        if self.current_index < len(self.poses) - 1:
            self.current_index += 1
            self.start_pose()

    def on_pose_finished(self):
        self.soundbank.play("over")
        if self.chk_auto_advance.isChecked():
            if self.current_index < len(self.poses) - 1:
                self.current_index += 1
                self.start_pose()
            else:
                self.pose_info.setText("Session Complete")
        else:
            self.pose_info.setText("Pose Finished (Manual Advance)")

    def update_display(self, secs: int):
        self.display.setText(seconds_to_hhmmss(secs))

    # -------- Soundbank --------

    def save_soundbank(self):
        fp, _ = QFileDialog.getSaveFileName(
            self,
            "Save Soundbank",
            str(self.data_dir),
            f"Soundbank (*.{SOUNDBANK_EXT})",
        )
        if not fp:
            return
        self.soundbank.export_soundbank(Path(fp))

    def load_soundbank(self):
        fp, _ = QFileDialog.getOpenFileName(
            self,
            "Load Soundbank",
            str(self.data_dir),
            f"Soundbank (*.{SOUNDBANK_EXT})",
        )
        if not fp:
            return
        self.soundbank.import_soundbank(Path(fp))


# -------------------- Main --------------------

def main():
    app = QApplication(sys.argv)
    w = TimerWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
