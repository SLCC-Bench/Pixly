"""Reusable UI building blocks."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def horizontal_rule(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


def make_header(
    title: str,
    subtitle: str,
    status_widget: QWidget,
    parent: QWidget | None = None,
) -> QFrame:
    """Top app bar with title block and status pill."""
    bar = QFrame(parent)
    bar.setObjectName("headerBar")

    layout = QHBoxLayout(bar)
    layout.setContentsMargins(4, 4, 4, 12)
    layout.setSpacing(16)

    title_block = QVBoxLayout()
    title_block.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setObjectName("appTitle")
    sub_lbl = QLabel(subtitle)
    sub_lbl.setObjectName("appSubtitle")
    title_block.addWidget(title_lbl)
    title_block.addWidget(sub_lbl)

    layout.addLayout(title_block)
    layout.addStretch()
    layout.addWidget(status_widget, alignment=Qt.AlignmentFlag.AlignVCenter)

    return bar


def make_region_chip(parent: QWidget | None = None) -> tuple[QFrame, QLabel]:
    """Highlighted capture target summary."""
    chip = QFrame(parent)
    chip.setObjectName("regionChip")
    layout = QVBoxLayout(chip)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(4)

    caption = QLabel("Capture target")
    caption.setObjectName("chipCaption")
    value = QLabel("No region selected")
    value.setObjectName("chipValue")
    value.setWordWrap(True)

    layout.addWidget(caption)
    layout.addWidget(value)
    return chip, value


def make_panel(
    title: str,
    *,
    subtitle: str | None = None,
    compact: bool = False,
    parent: QWidget | None = None,
) -> tuple[QFrame, QVBoxLayout]:
    """Card-style section with optional subtitle."""
    panel = QFrame(parent)
    panel.setObjectName("panel")
    outer = QVBoxLayout(panel)
    if compact:
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
    else:
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

    head = QVBoxLayout()
    head.setSpacing(4)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    head.addWidget(heading)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("sectionSubtitle")
        sub.setWordWrap(True)
        head.addWidget(sub)
    outer.addLayout(head)

    body = QVBoxLayout()
    body.setSpacing(10 if compact else 12)
    outer.addLayout(body)
    return panel, body


def make_form_row(
    label_text: str,
    widget: QWidget,
    *,
    label_width: int = 96,
) -> QHBoxLayout:
    """Label + control on one row; control expands to fill available width."""
    row = QHBoxLayout()
    row.setSpacing(10)
    label = QLabel(label_text)
    label.setObjectName("fieldLabel")
    label.setFixedWidth(label_width)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )
    row.addWidget(label)
    row.addWidget(widget, stretch=1)
    return row


def make_audio_track_row(
    title: str,
    record: QCheckBox,
    mute: QCheckBox,
) -> QHBoxLayout:
    """One audio source: title on the left, capture + mute on the right."""
    row = QHBoxLayout()
    row.setSpacing(10)
    name = QLabel(title)
    name.setObjectName("fieldLabel")
    name.setMinimumWidth(72)
    record.setText("Capture")
    mute.setText("Mute")
    row.addWidget(name)
    row.addStretch(1)
    row.addWidget(record)
    row.addWidget(mute)
    return row


def make_footer(text: str, parent: QWidget | None = None) -> QFrame:
    foot = QFrame(parent)
    foot.setObjectName("footerBar")
    layout = QHBoxLayout(foot)
    layout.setContentsMargins(12, 10, 12, 4)
    lbl = QLabel(text)
    lbl.setObjectName("footerText")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(True)
    layout.addWidget(lbl)
    return foot
