"""Main application window."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QMetaObject, QPoint, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QClipboard, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from screen_gif_recorder.capture.audio_recorder import (
    AudioCaptureConfig,
    AudioCaptureResult,
    AudioRecorder,
)
from screen_gif_recorder.capture.screen_recorder import CaptureRegion, RecorderSettings, ScreenRecorder
from screen_gif_recorder.export.mp4_exporter import ffmpeg_available, ffmpeg_install_hint
from screen_gif_recorder.ui.screen_picker import ScreenPickerDialog, screen_label
from screen_gif_recorder.ui.window_picker import WindowPickerDialog
from screen_gif_recorder.utils.macos_windows import (
    WindowInfo,
    focus_browser_window,
    macos_window_api_available,
    refresh_window_bounds,
)
from screen_gif_recorder.ui.region_selector import (
    LogicalRegion,
    RegionSelectorOverlay,
    region_for_screen,
    warm_up_displays,
)
from screen_gif_recorder.ui.countdown_overlay import RecordingCountdownOverlay
from screen_gif_recorder.ui.preview_player import RecordingPreview
from screen_gif_recorder.ui.styles import APP_STYLESHEET
from screen_gif_recorder.ui.widgets import (
    horizontal_rule,
    make_audio_track_row,
    make_footer,
    make_form_row,
    make_header,
    make_panel,
    make_region_chip,
)
from screen_gif_recorder.ui.export_thread import ExportThread
from screen_gif_recorder.utils.audio_devices import (
    find_system_audio_device,
    sounddevice_available,
    system_audio_setup_hint,
)
from screen_gif_recorder.utils.coordinates import logical_to_capture_region, region_description
from screen_gif_recorder.utils.macos_global_hotkey import (
    global_stop_hotkey_available,
    install_global_stop_hotkey,
    uninstall_global_stop_hotkey,
)
from screen_gif_recorder.utils.permissions import (
    accessibility_hint_message,
    check_accessibility_permission,
    check_screen_capture_permission,
    open_screen_recording_preferences,
    permission_hint_message,
    request_accessibility_permission,
)
from screen_gif_recorder.utils.temp_files import TempWorkspace


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pixly — Screen to GIF")
        self.setMinimumSize(960, 600)
        self.resize(1120, 680)

        self._logical_region: LogicalRegion | None = None
        self._capture_region: CaptureRegion | None = None
        self._recorder: ScreenRecorder | None = None
        self._last_frames: list[Image.Image] = []
        self._workspace = TempWorkspace()
        self._export_thread: ExportThread | None = None
        self._selector: RegionSelectorOverlay | None = None
        self._select_timer: QTimer | None = None
        self._countdown_overlay: RecordingCountdownOverlay | None = None
        self._countdown_prep_timer: QTimer | None = None
        self._recording_prep_active = False
        self._audio_recorder: AudioRecorder | None = None
        self._last_audio: AudioCaptureResult | None = None
        self._tracked_window: WindowInfo | None = None
        self._stop_hotkey_accessibility_prompted = False

        self._build_ui()
        self._wire_shortcuts()
        self._check_permissions_on_start()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 14)

        self._status = QLabel("Idle")
        self._status.setObjectName("statusIdle")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            make_header("Pixly", "Screen to GIF recorder", self._status)
        )

        body = QHBoxLayout()
        body.setSpacing(14)

        preview_panel, preview_body = make_panel(
            "Preview",
            subtitle="Scrub the timeline after you stop recording",
        )
        self._preview = RecordingPreview()
        preview_body.addWidget(self._preview, stretch=1)
        body.addWidget(preview_panel, stretch=3)

        controls = QWidget()
        controls.setMinimumWidth(340)
        controls.setMaximumWidth(400)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)

        source_panel, source_body = make_panel(
            "Capture",
            subtitle="Choose what to record",
            compact=True,
        )
        region_chip, self._region_label = make_region_chip()
        source_body.addWidget(region_chip)

        source_btns = QHBoxLayout()
        source_btns.setSpacing(6)
        self._btn_select = QPushButton("Area")
        self._btn_browser = QPushButton("Window")
        self._btn_display = QPushButton("Display")
        for btn in (self._btn_select, self._btn_browser, self._btn_display):
            btn.setObjectName("sourceBtn")
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            source_btns.addWidget(btn)
        source_body.addLayout(source_btns)
        controls_layout.addWidget(source_panel)

        record_panel, record_body = make_panel("Record & export", compact=True)
        record_row = QHBoxLayout()
        record_row.setSpacing(8)
        self._btn_start = QPushButton("Start")
        self._btn_start.setObjectName("primaryBtn")
        self._btn_start.setMinimumHeight(40)
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setObjectName("dangerBtn")
        self._btn_stop.setMinimumHeight(40)
        self._btn_stop.setToolTip("Stop recording (⌘. or Esc)")
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._btn_stop.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        record_row.addWidget(self._btn_start, stretch=2)
        record_row.addWidget(self._btn_stop, stretch=1)
        record_body.addLayout(record_row)

        record_body.addWidget(horizontal_rule())

        export_lbl = QLabel("Export")
        export_lbl.setObjectName("subsectionTitle")
        record_body.addWidget(export_lbl)
        export_row = QHBoxLayout()
        export_row.setSpacing(6)
        self._btn_save_gif = QPushButton("Save GIF")
        self._btn_save_mp4 = QPushButton("Save MP4")
        for btn in (self._btn_save_gif, self._btn_save_mp4):
            btn.setObjectName("secondaryBtn")
            btn.setMinimumHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            export_row.addWidget(btn)
        record_body.addLayout(export_row)
        controls_layout.addWidget(record_panel)

        settings_panel, settings_body = make_panel(
            "Quality",
            subtitle="Capture and export",
            compact=True,
        )
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(5, 30)
        self._fps_spin.setValue(12)
        self._scale_combo = QComboBox()
        self._scale_combo.addItems(["1× Full", "0.75×", "0.5×"])
        self._quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._quality_slider.setRange(0, 100)
        self._quality_slider.setValue(55)
        self._quality_slider.setToolTip(
            "Lower = smaller files at full resolution"
        )
        self._quality_label = QLabel("55")
        self._quality_label.setObjectName("mutedLabel")
        self._quality_label.setFixedWidth(28)
        self._quality_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._quality_slider.valueChanged.connect(
            lambda v: self._quality_label.setText(str(v))
        )
        self._clipboard_check = QCheckBox("Copy GIF to clipboard after save")
        self._clipboard_check.setChecked(True)

        settings_body.addLayout(make_form_row("Frame rate", self._fps_spin))
        settings_body.addLayout(make_form_row("Scale", self._scale_combo))

        compression_row = QHBoxLayout()
        compression_row.setSpacing(10)
        compression_lbl = QLabel("Compression")
        compression_lbl.setObjectName("fieldLabel")
        compression_lbl.setFixedWidth(96)
        compression_lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        compression_row.addWidget(compression_lbl)
        compression_row.addWidget(self._quality_slider, stretch=1)
        compression_row.addWidget(self._quality_label)
        settings_body.addLayout(compression_row)
        settings_body.addWidget(self._clipboard_check)
        controls_layout.addWidget(settings_panel)

        audio_panel, audio_body = make_panel(
            "Audio",
            subtitle="Included in MP4 only",
            compact=True,
        )
        self._record_mic = QCheckBox()
        self._mute_mic = QCheckBox()
        self._record_system = QCheckBox()
        self._mute_system = QCheckBox()
        audio_body.addLayout(
            make_audio_track_row("Microphone", self._record_mic, self._mute_mic)
        )
        audio_body.addLayout(
            make_audio_track_row("System audio", self._record_system, self._mute_system)
        )
        self._mute_mic.setEnabled(False)
        self._mute_system.setEnabled(False)
        self._record_mic.toggled.connect(self._on_record_mic_toggled)
        self._record_system.toggled.connect(self._on_record_system_toggled)
        self._mute_mic.toggled.connect(self._on_mute_mic_toggled)
        self._mute_system.toggled.connect(self._on_mute_system_toggled)

        audio_hint = QLabel(
            "System audio needs a loopback device (e.g. BlackHole) on macOS."
        )
        audio_hint.setObjectName("mutedLabel")
        audio_hint.setWordWrap(True)
        audio_hint.setToolTip(system_audio_setup_hint())
        audio_body.addWidget(audio_hint)

        if not sounddevice_available():
            for box in (
                self._record_mic,
                self._mute_mic,
                self._record_system,
                self._mute_system,
            ):
                box.setEnabled(False)
            audio_hint.setText("Install sounddevice for audio capture.")
        elif find_system_audio_device() is None:
            self._record_system.setToolTip(system_audio_setup_hint())

        controls_layout.addWidget(audio_panel)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        controls_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        controls_scroll.setWidget(controls)
        controls_scroll.setMinimumWidth(356)
        controls_scroll.setMaximumWidth(416)
        body.addWidget(controls_scroll, stretch=0)

        layout.addLayout(body, stretch=1)

        layout.addWidget(
            make_footer(
                "⌘R Start  ·  3s countdown  ·  ⌘. or Esc Stop  ·  GIF or MP4"
            )
        )

        # Signals
        self._btn_select.clicked.connect(self._on_select_area)
        self._btn_browser.clicked.connect(self._on_select_browser_window)
        self._btn_display.clicked.connect(self._on_select_display)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_save_gif.clicked.connect(lambda: self._on_save("gif"))
        self._btn_save_mp4.clicked.connect(lambda: self._on_save("mp4"))

        self._update_button_states(recording=False)

        if not ffmpeg_available():
            self._btn_save_mp4.setToolTip(
                "MP4 needs ffmpeg — run: brew install ffmpeg  OR  pip install imageio-ffmpeg"
            )
        if not macos_window_api_available():
            self._btn_browser.setEnabled(False)

    def _wire_shortcuts(self) -> None:
        start = QShortcut(QKeySequence("Meta+R"), self)
        start.setContext(Qt.ShortcutContext.WindowShortcut)
        start.activated.connect(self._on_start)

        stop_cmd = QShortcut(
            QKeySequence(Qt.Modifier.META | Qt.Key.Key_Period), self
        )
        stop_cmd.setContext(Qt.ShortcutContext.ApplicationShortcut)
        stop_cmd.activated.connect(self._on_stop_shortcut)

        stop_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        stop_esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        stop_esc.activated.connect(self._on_stop_shortcut)

    def _check_permissions_on_start(self) -> None:
        if not check_screen_capture_permission():
            QMessageBox.warning(
                self,
                "Screen Recording Permission",
                permission_hint_message(),
                QMessageBox.StandardButton.Ok,
            )
            open_screen_recording_preferences()

    def _scale_factor(self) -> float:
        text = self._scale_combo.currentText()
        if "0.75" in text:
            return 0.75
        if "0.5" in text:
            return 0.5
        return 1.0

    def _set_status(
        self,
        recording: bool = False,
        *,
        processing: bool = False,
        exporting: bool = False,
        export_completed: bool = False,
        idle: bool = False,
    ) -> None:
        if exporting:
            self._status.setObjectName("statusExporting")
        elif export_completed:
            self._status.setText("Export Completed")
            self._status.setObjectName("statusExportCompleted")
        elif processing:
            self._status.setText("Processing")
            self._status.setObjectName("statusProcessing")
        elif recording:
            self._status.setText("Recording")
            self._status.setObjectName("statusRecording")
        elif idle:
            self._status.setText("Idle")
            self._status.setObjectName("statusIdle")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _is_counting_down(self) -> bool:
        return self._countdown_overlay is not None

    def _update_button_states(self, recording: bool) -> None:
        counting = self._is_counting_down()
        self._btn_select.setEnabled(not recording and not counting)
        self._btn_browser.setEnabled(
            not recording and not counting and macos_window_api_available()
        )
        self._btn_display.setEnabled(not recording and not counting)
        self._btn_start.setEnabled(
            not recording and not counting and self._capture_region is not None
        )
        self._btn_stop.setEnabled(recording or counting)
        has_frames = len(self._last_frames) > 0
        self._btn_save_gif.setEnabled(has_frames and not recording)
        self._btn_save_mp4.setEnabled(
            has_frames and not recording and ffmpeg_available()
        )
        self._fps_spin.setEnabled(not recording)
        self._scale_combo.setEnabled(not recording)
        audio_enabled = not recording and not counting
        for w in (
            self._record_mic,
            self._mute_mic,
            self._record_system,
            self._mute_system,
        ):
            w.setEnabled(audio_enabled and sounddevice_available())
        if audio_enabled and sounddevice_available():
            self._mute_mic.setEnabled(self._record_mic.isChecked())
            self._mute_system.setEnabled(self._record_system.isChecked())

    def _on_record_mic_toggled(self, checked: bool) -> None:
        self._mute_mic.setEnabled(checked and sounddevice_available())

    def _on_record_system_toggled(self, checked: bool) -> None:
        self._mute_system.setEnabled(checked and sounddevice_available())

    def _on_mute_mic_toggled(self, checked: bool) -> None:
        if self._audio_recorder is not None:
            self._audio_recorder.mic_muted = checked

    def _on_mute_system_toggled(self, checked: bool) -> None:
        if self._audio_recorder is not None:
            self._audio_recorder.system_muted = checked

    def _audio_capture_config(self) -> AudioCaptureConfig:
        return AudioCaptureConfig(
            record_mic=self._record_mic.isChecked(),
            record_system=self._record_system.isChecked(),
            mute_mic=self._mute_mic.isChecked(),
            mute_system=self._mute_system.isChecked(),
        )

    def _start_audio_capture(self) -> None:
        config = self._audio_capture_config()
        if not config.record_mic and not config.record_system:
            return
        if not sounddevice_available():
            return

        if config.record_system and find_system_audio_device() is None:
            QMessageBox.warning(self, "System audio", system_audio_setup_hint())
            self._record_system.setChecked(False)
            config = self._audio_capture_config()
            if not config.record_mic and not config.record_system:
                return

        try:
            self._audio_recorder = AudioRecorder(config, self._workspace.path)
            self._audio_recorder.start()
        except Exception as exc:
            self._audio_recorder = None
            QMessageBox.warning(
                self,
                "Audio capture",
                f"Could not start audio recording:\n{exc}\n\nVideo will still be captured.",
            )

    def _stop_audio_capture(self) -> None:
        if self._audio_recorder is None:
            self._last_audio = None
            return
        try:
            self._last_audio = self._audio_recorder.stop()
        except Exception:
            self._last_audio = None
        self._audio_recorder = None

    def _stop_select_timer(self) -> None:
        if self._select_timer is not None:
            self._select_timer.stop()
            self._select_timer.deleteLater()
            self._select_timer = None

    @pyqtSlot()
    def _on_select_area(self) -> None:
        if self._selector is not None:
            return

        self._stop_select_timer()

        overlay = RegionSelectorOverlay()
        self._selector = overlay
        overlay.region_selected.connect(self._on_region_selected)
        overlay.cancelled.connect(self._on_select_cancelled)
        overlay.destroyed.connect(self._on_selector_destroyed)

        QGuiApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)

        warm_up_displays()
        # Invisible overlays on all displays first — stops macOS from switching
        # monitors when Pixly moves aside. Minimize (not hide) is gentler than hide().
        overlay.prepare_invisible_panels()
        self.showMinimized()
        QGuiApplication.processEvents()

        self._select_timer = QTimer(self)
        self._select_timer.setSingleShot(True)

        def _reveal_overlay() -> None:
            if self._selector is overlay:
                overlay.reveal_with_desktop()

        self._select_timer.timeout.connect(_reveal_overlay)
        self._select_timer.start(280)

    @pyqtSlot()
    def _on_select_browser_window(self) -> None:
        dialog = WindowPickerDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        win = dialog.selected_window
        if win is None:
            return
        self._tracked_window = win
        self._apply_region(win.to_logical_region())
        self._region_label.setText(f"Window: {win.display_name}")
        # Refine bounds in the background (picker uses a fast path without AppleScript).
        QTimer.singleShot(0, self._refresh_tracked_window_bounds_quiet)

    def _apply_display_screen(self, screen: QScreen) -> None:
        """Set capture region from a display (optimistic — uses current geometry)."""
        self._tracked_window = None
        self._apply_region(region_for_screen(screen))
        screens = QGuiApplication.screens()
        index = screens.index(screen) if screen in screens else 0
        self._region_label.setText(f"Display: {screen_label(screen, index)}")

    def _refine_display_region_quiet(self, screen: QScreen) -> None:
        """Re-read display geometry after selection without blocking the UI."""
        warm_up_displays()
        screens = QGuiApplication.screens()
        if screen not in screens:
            return
        self._apply_display_screen(screen)

    @pyqtSlot()
    def _on_select_display(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            QMessageBox.warning(self, "No display", "Could not detect a display.")
            return

        if len(screens) == 1:
            screen = screens[0]
            self._apply_display_screen(screen)
            QTimer.singleShot(0, lambda: self._refine_display_region_quiet(screen))
            return

        dialog = ScreenPickerDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        screen = dialog.selected_screen
        if screen is None:
            return

        self._apply_display_screen(screen)
        QTimer.singleShot(0, lambda: self._refine_display_region_quiet(screen))

    def _restore_main_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def _on_region_selected(self, region: LogicalRegion) -> None:
        self._stop_select_timer()
        self._tracked_window = None
        self._apply_region(region)
        self._restore_main_window()

    def _on_select_cancelled(self) -> None:
        self._stop_select_timer()
        QGuiApplication.restoreOverrideCursor()
        self._restore_main_window()

    def _on_selector_destroyed(self) -> None:
        self._stop_select_timer()
        self._selector = None
        QGuiApplication.restoreOverrideCursor()
        self._restore_main_window()

    def _apply_region(self, region: LogicalRegion) -> None:
        self._logical_region = region
        cx = region.x + region.width // 2
        cy = region.y + region.height // 2
        screen = QGuiApplication.screenAt(QPoint(cx, cy)) or QGuiApplication.primaryScreen()
        self._capture_region = logical_to_capture_region(region, screen)
        self._region_label.setText(region_description(region, screen))
        self._update_button_states(recording=False)

    def _refresh_tracked_window(self) -> bool:
        """Re-read the browser window bounds (required for external displays)."""
        if self._tracked_window is None:
            return True
        refreshed = refresh_window_bounds(self._tracked_window)
        if refreshed is None:
            return False
        self._tracked_window = refreshed
        self._apply_region(refreshed.to_logical_region())
        self._region_label.setText(f"Window: {refreshed.display_name}")
        return True

    def _refresh_tracked_window_bounds_quiet(self) -> None:
        """Update window bounds after picker without blocking the UI."""
        if self._tracked_window is None:
            return
        refreshed = refresh_window_bounds(self._tracked_window)
        if refreshed is None:
            return
        self._tracked_window = refreshed
        self._apply_region(refreshed.to_logical_region())
        self._region_label.setText(f"Window: {refreshed.display_name}")

    @pyqtSlot()
    def _on_start(self) -> None:
        if self._recorder is not None or self._is_counting_down():
            return
        if self._capture_region is None:
            QMessageBox.information(self, "Select area", "Choose a screen region first.")
            return
        if not check_screen_capture_permission():
            QMessageBox.warning(self, "Permission", permission_hint_message())
            open_screen_recording_preferences()
            return

        if self._tracked_window is not None:
            if not self._refresh_tracked_window():
                QMessageBox.warning(
                    self,
                    "Window not found",
                    "The window is no longer available. Click Window to select it again.",
                )
                return
            # Raise on its current monitor without activate (avoids moving to built-in display)
            focus_browser_window(self._tracked_window, activate_app=False)
            QGuiApplication.processEvents()
            QTimer.singleShot(250, self._prepare_browser_recording)
            return

        self._start_recording_countdown()

    def _prepare_browser_recording(self) -> None:
        if self._tracked_window is None:
            self._start_recording_countdown()
            return
        if not self._refresh_tracked_window():
            QMessageBox.warning(
                self,
                "Window not found",
                "The window moved or closed. Select Window again.",
            )
            return
        self._start_recording_countdown()

    def _stop_countdown_prep_timer(self) -> None:
        if self._countdown_prep_timer is not None:
            self._countdown_prep_timer.stop()
            self._countdown_prep_timer.deleteLater()
            self._countdown_prep_timer = None

    def _activate_stop_hotkey(self) -> None:
        def _dispatch_stop() -> None:
            # Global NSEvent monitors run off the Qt main thread; marshal back safely.
            QMetaObject.invokeMethod(
                self,
                "_on_stop_shortcut",
                Qt.ConnectionType.QueuedConnection,
            )

        installed, global_ok = install_global_stop_hotkey(_dispatch_stop)
        if not installed:
            tip = "Stop with Esc while Pixly is focused"
            if not global_stop_hotkey_available():
                tip += " — reinstall Pixly (AppKit missing from bundle)"
            self._btn_stop.setToolTip(tip)
        elif not global_ok:
            self._btn_stop.setToolTip(
                "Stop: Esc anytime · enable Pixly under System Settings → "
                "Privacy & Security → Accessibility for global ⌘."
            )
            if not self._stop_hotkey_accessibility_prompted:
                self._stop_hotkey_accessibility_prompted = True
                if not check_accessibility_permission():
                    request_accessibility_permission(prompt=True)
                    QMessageBox.information(
                        self,
                        "Accessibility for ⌘.",
                        accessibility_hint_message(),
                    )
        else:
            self._btn_stop.setToolTip("Stop recording (⌘. or Esc)")

    def _deactivate_stop_hotkey(self) -> None:
        uninstall_global_stop_hotkey()
        self._btn_stop.setToolTip("Stop recording (⌘. or Esc)")

    def _cancel_countdown(self) -> None:
        self._recording_prep_active = False
        self._stop_countdown_prep_timer()
        if self._countdown_overlay is not None:
            self._countdown_overlay.cancel()

    def _start_recording_countdown(self) -> None:
        if self._capture_region is None or self._countdown_overlay is not None:
            return

        self._recording_prep_active = True
        self._activate_stop_hotkey()
        self._update_button_states(recording=False)

        # Minimize first so the countdown runs over the desktop, not on top of Pixly
        self.showMinimized()
        QGuiApplication.processEvents()

        self._stop_countdown_prep_timer()
        self._countdown_prep_timer = QTimer(self)
        self._countdown_prep_timer.setSingleShot(True)
        self._countdown_prep_timer.timeout.connect(self._present_recording_countdown)
        self._countdown_prep_timer.start(450)

    def _present_recording_countdown(self) -> None:
        self._countdown_prep_timer = None
        if not self._recording_prep_active or self._capture_region is None:
            return
        if self._countdown_overlay is not None:
            return

        self._preview.set_message("Get ready…")
        self._status.setText("Starting in 3")
        self._status.setObjectName("statusExporting")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

        overlay = RecordingCountdownOverlay()
        self._countdown_overlay = overlay
        overlay.finished.connect(self._on_countdown_finished)
        overlay.cancelled.connect(self._on_countdown_cancelled)
        overlay.destroyed.connect(self._on_countdown_destroyed)
        overlay.start(3)

    def _on_countdown_finished(self) -> None:
        self._begin_recording()

    def _on_countdown_cancelled(self) -> None:
        self._recording_prep_active = False
        self._deactivate_stop_hotkey()
        self._restore_main_window()
        self._preview.set_message("Recording preview")
        self._set_status(idle=True)
        self._update_button_states(recording=False)

    def _on_countdown_destroyed(self) -> None:
        self._countdown_overlay = None

    @pyqtSlot()
    def _on_stop_shortcut(self) -> None:
        if self._selector is not None:
            self._selector.close()
            return
        if self._is_counting_down():
            self._cancel_countdown()
            return
        self._on_stop()

    def _begin_recording(self) -> None:
        if self._capture_region is None:
            return

        if self._tracked_window is not None and not self._refresh_tracked_window():
            QMessageBox.warning(
                self,
                "Window not found",
                "Could not update the window region. Select Window again.",
            )
            return

        self._last_frames.clear()
        self._preview.clear()
        self._workspace.start()
        settings = RecorderSettings(
            fps=float(self._fps_spin.value()),
            scale=self._scale_factor(),
        )
        self._preview.set_message(
            "Recording… Press ⌘. or Esc to stop (works while other apps are focused)"
        )
        if not self.isMinimized():
            self.showMinimized()

        self._recorder = ScreenRecorder(
            self._capture_region,
            settings,
            on_frame=None,
        )
        self._recorder.start()
        self._start_audio_capture()
        self._activate_stop_hotkey()
        self._set_status(recording=True)
        self._update_button_states(recording=True)

    @pyqtSlot()
    def _on_stop(self) -> None:
        if self._is_counting_down():
            self._cancel_countdown()
            return
        if self._recorder is None:
            return
        recorder = self._recorder
        self._recorder = None
        recorder.stop()
        self._last_frames = recorder.frames
        self._stop_audio_capture()

        self._recording_prep_active = False
        self._deactivate_stop_hotkey()
        self._set_status(processing=True)
        self._update_button_states(recording=False)
        self._restore_main_window()

        if self._last_frames:
            fps = float(self._fps_spin.value())
            frames = self._last_frames
            n = len(frames)
            dur = n / max(fps, 1.0)
            self._region_label.setText(
                f"{self._region_label.text()}  •  {n} frames (~{dur:.1f}s)"
            )

            def _load_preview() -> None:
                self._preview.load_recording(frames, fps)
                self._set_status(idle=True)

            QTimer.singleShot(100, _load_preview)
        else:
            self._set_status(idle=True)

    def _on_save(self, fmt: str) -> None:
        if not self._last_frames:
            return
        if fmt == "mp4" and not ffmpeg_available():
            QMessageBox.warning(self, "MP4 export", ffmpeg_install_hint())
            return

        if (
            fmt == "gif"
            and self._last_audio is not None
            and self._last_audio.has_audio()
        ):
            QMessageBox.information(
                self,
                "Audio not in GIF",
                "Recorded audio is included only when you save as MP4.",
            )

        default_name = "recording.gif" if fmt == "gif" else "recording.mp4"
        filter_str = "GIF (*.gif)" if fmt == "gif" else "MP4 (*.mp4)"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save recording",
            str(Path.home() / "Desktop" / default_name),
            filter_str,
        )
        if not path:
            return

        if self._export_thread is not None and self._export_thread.isRunning():
            QMessageBox.warning(
                self,
                "Export in progress",
                "Please wait for the current export to finish.",
            )
            return

        self._preview.stop()
        self._set_busy(True)
        QApplication.processEvents()

        frames_copy = [f.copy() for f in self._last_frames]
        QApplication.processEvents()

        audio = self._last_audio if fmt == "mp4" else None

        thread = ExportThread(
            frames_copy,
            Path(path),
            fmt,
            float(self._fps_spin.value()),
            self._quality_slider.value(),
            audio=audio,
            parent=self,
        )
        thread.progress.connect(self._on_export_progress)
        thread.finished_ok.connect(lambda p: self._on_export_done(p, fmt))
        thread.failed.connect(self._on_export_failed)
        thread.finished.connect(self._on_export_thread_finished)

        self._export_thread = thread
        thread.start()

    def _on_export_progress(self, current: int, total: int) -> None:
        self._status.setText(f"Exporting {current}/{total}")
        self._set_status(exporting=True)
        QApplication.processEvents()

    def _on_export_thread_finished(self) -> None:
        self._export_thread = None

    def _set_busy(self, busy: bool) -> None:
        self._btn_save_gif.setEnabled(not busy and len(self._last_frames) > 0)
        self._btn_save_mp4.setEnabled(
            not busy and len(self._last_frames) > 0 and ffmpeg_available()
        )
        if busy:
            self._set_status(processing=True)

    def _on_export_done(self, path: str, fmt: str) -> None:
        self._set_busy(False)
        self._set_status(export_completed=True)
        self._update_button_states(recording=False)

        if fmt == "gif" and self._clipboard_check.isChecked():
            self._copy_gif_to_clipboard(path)

        self._workspace.cleanup()
        self._last_audio = None

        QMessageBox.information(self, "Saved", f"Recording saved to:\n{path}")

    def _on_export_failed(self, message: str) -> None:
        self._set_busy(False)
        self._set_status(idle=True)
        self._update_button_states(recording=False)
        QMessageBox.critical(self, "Export failed", message)
        # Keep workspace so the user can retry export with audio

    def _copy_gif_to_clipboard(self, path: str) -> None:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            QGuiApplication.clipboard().setPixmap(
                pixmap, QClipboard.Mode.Clipboard
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._preview.stop()
        self._cancel_countdown()
        self._deactivate_stop_hotkey()
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
        if self._audio_recorder is not None:
            try:
                self._audio_recorder.stop()
            except Exception:
                pass
            self._audio_recorder = None
        if self._export_thread is not None and self._export_thread.isRunning():
            self._export_thread.requestInterruption()
            self._export_thread.wait(3000)
        self._workspace.cleanup()
        super().closeEvent(event)


def create_main_window() -> MainWindow:
    win = MainWindow()
    win.setStyleSheet(APP_STYLESHEET)
    return win
