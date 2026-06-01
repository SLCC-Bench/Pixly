"""Application-wide Qt stylesheet — Pixly design system."""

APP_STYLESHEET = """
/* —— Canvas —— */
QMainWindow {
    background-color: #09090b;
}
QWidget {
    background-color: transparent;
    color: #f4f4f5;
    font-family: -apple-system, "SF Pro Text", "Inter", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

/* —— Header —— */
QFrame#headerBar {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #27272a;
}
QLabel#appTitle {
    font-size: 22px;
    font-weight: 700;
    color: #fafafa;
    letter-spacing: -0.02em;
}
QLabel#appSubtitle {
    font-size: 12px;
    color: #71717a;
}

/* —— Footer —— */
QFrame#footerBar {
    background-color: #0f0f12;
    border: 1px solid #27272a;
    border-radius: 10px;
}
QLabel#footerText {
    color: #71717a;
    font-size: 11px;
}

/* —— Panels —— */
QFrame#panel {
    background-color: #131316;
    border: 1px solid #27272a;
    border-radius: 12px;
}
QLabel#sectionTitle {
    color: #fafafa;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.02em;
}
QLabel#sectionSubtitle {
    color: #71717a;
    font-size: 12px;
}
QLabel#subsectionTitle {
    color: #a1a1aa;
    font-size: 11px;
    font-weight: 600;
    text-transform: none;
    padding-top: 4px;
}
QLabel#fieldLabel {
    color: #a1a1aa;
    font-size: 12px;
    font-weight: 500;
}
QLabel#mutedLabel {
    color: #71717a;
    font-size: 12px;
}
QFrame#divider {
    background-color: #27272a;
    border: none;
    max-height: 1px;
}

/* —— Region chip —— */
QFrame#regionChip {
    background-color: #1a1a1f;
    border: 1px solid #3f3f46;
    border-radius: 10px;
}
QLabel#chipCaption {
    color: #71717a;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
}
QLabel#chipValue {
    color: #e4e4e7;
    font-size: 13px;
    font-weight: 500;
}

/* —— Status pills —— */
QLabel#statusIdle,
QLabel#statusProcessing,
QLabel#statusRecording,
QLabel#statusExporting,
QLabel#statusExportCompleted {
    font-weight: 600;
    font-size: 11px;
    padding: 7px 16px;
    border-radius: 20px;
    min-width: 72px;
}
QLabel#statusIdle {
    background-color: #14532d;
    color: #86efac;
    border: 1px solid #166534;
}
QLabel#statusProcessing {
    background-color: #422006;
    color: #fcd34d;
    border: 1px solid #713f12;
}
QLabel#statusRecording {
    background-color: #450a0a;
    color: #fca5a5;
    border: 1px solid #7f1d1d;
}
QLabel#statusExporting {
    background-color: #1e1b4b;
    color: #a5b4fc;
    border: 1px solid #312e81;
}
QLabel#statusExportCompleted {
    background-color: #14532d;
    color: #bbf7d0;
    border: 1px solid #166534;
}

/* —— Buttons —— */
QPushButton {
    background-color: #1a1a1f;
    border: 1px solid #3f3f46;
    border-radius: 10px;
    padding: 8px 14px;
    color: #e4e4e7;
    min-height: 20px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #27272a;
    border-color: #52525b;
}
QPushButton:pressed {
    background-color: #18181b;
}
QPushButton:disabled {
    color: #52525b;
    background-color: #131316;
    border-color: #27272a;
}
QPushButton#primaryBtn {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 20px;
}
QPushButton#primaryBtn:hover {
    background-color: #60a5fa;
    border-color: #60a5fa;
}
QPushButton#primaryBtn:disabled {
    background-color: #1e3a5f;
    border-color: #1e3a5f;
    color: #64748b;
}
QPushButton#dangerBtn {
    background-color: #dc2626;
    border-color: #dc2626;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 18px;
}
QPushButton#dangerBtn:hover {
    background-color: #ef4444;
    border-color: #ef4444;
}
QPushButton#dangerBtn:disabled {
    background-color: #3f1515;
    border-color: #3f1515;
    color: #7f4a4a;
}
QPushButton#secondaryBtn,
QPushButton#sourceBtn {
    background-color: transparent;
    border: 1px solid #3f3f46;
    color: #d4d4d8;
    padding: 8px 12px;
    min-width: 0;
    font-size: 12px;
}
QPushButton#secondaryBtn:hover,
QPushButton#sourceBtn:hover {
    background-color: #1a1a1f;
    border-color: #52525b;
    color: #fafafa;
}
QPushButton#iconBtn {
    background-color: #1a1a1f;
    border: 1px solid #3f3f46;
    border-radius: 8px;
    padding: 0;
    min-width: 0;
    font-size: 13px;
    color: #d4d4d8;
}
QPushButton#iconBtn:hover {
    background-color: #27272a;
}
QPushButton#playBtn {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    font-weight: 600;
    color: #fafafa;
    min-width: 0;
    padding: 0 16px;
}
QPushButton#playBtn:hover {
    background-color: #3f3f46;
}

/* —— Preview —— */
QLabel#previewLabel {
    background-color: #09090b;
    border: 1px solid #27272a;
    border-radius: 10px;
    color: #52525b;
    font-size: 14px;
}
QFrame#playerChrome {
    background-color: transparent;
    border: none;
}
QFrame#transportBar {
    background-color: #1a1a1f;
    border: 1px solid #27272a;
    border-radius: 10px;
}
QLabel#timeLabel {
    color: #a1a1aa;
    font-family: "SF Mono", "Menlo", "Consolas", monospace;
    font-size: 11px;
}

/* —— Form controls —— */
QComboBox, QSpinBox {
    background-color: #1a1a1f;
    border: 1px solid #3f3f46;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 22px;
    color: #f4f4f5;
    selection-background-color: #3b82f6;
}
QComboBox:hover, QSpinBox:hover {
    border-color: #52525b;
}
QComboBox:focus, QSpinBox:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down {
    border: none;
    width: 28px;
}
QComboBox QAbstractItemView {
    background-color: #1a1a1f;
    border: 1px solid #3f3f46;
    selection-background-color: #3b82f6;
    color: #f4f4f5;
}
QCheckBox {
    spacing: 10px;
    color: #d4d4d8;
    font-size: 13px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #52525b;
    background: #1a1a1f;
}
QCheckBox::indicator:hover {
    border-color: #71717a;
}
QCheckBox::indicator:checked {
    background: #3b82f6;
    border-color: #3b82f6;
}
QCheckBox::indicator:disabled {
    background: #131316;
    border-color: #27272a;
}

/* —— Sliders —— */
QSlider::groove:horizontal {
    height: 4px;
    background: #27272a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px;
    height: 12px;
    margin: -4px 0;
    background: #a1a1aa;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover {
    background: #fafafa;
}
QSlider#timelineSlider {
    min-height: 28px;
}
QSlider#timelineSlider::groove:horizontal {
    height: 5px;
    background: #27272a;
    border-radius: 3px;
}
QSlider#timelineSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 3px;
}
QSlider#timelineSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    background: #ffffff;
    border: 2px solid #3b82f6;
    border-radius: 7px;
}

/* —— Scroll —— */
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 6px 2px;
}
QScrollBar::handle:vertical {
    background: #3f3f46;
    border-radius: 3px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover {
    background: #52525b;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
"""
