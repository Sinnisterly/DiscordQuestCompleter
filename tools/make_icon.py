"""Generate the application icon.

    python tools/make_icon.py

Draws the mark at several sizes and packs them into dqc/data/icon.ico. Windows
picks the size it needs, so the small ones are drawn with less detail rather
than being scaled down from the large one.
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter,
    QPainterPath, QPolygonF,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'dqc' / 'data' / 'icon.ico'

SIZES = [16, 24, 32, 48, 64, 128, 256]
ACCENT = '#5865f2'
DEEP = '#3d47c4'
WHITE = '#ffffff'


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # Rounded square background, lit from the top.
    radius = size * 0.22
    body = QPainterPath()
    body.addRoundedRect(QRectF(0, 0, size, size), radius, radius)

    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0.0, QColor(ACCENT))
    gradient.setColorAt(1.0, QColor(DEEP))
    painter.fillPath(body, QBrush(gradient))

    # Play triangle, the one shape that survives at 16 pixels.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(WHITE)))
    w, h = size * 0.30, size * 0.34
    cx, cy = size * 0.53, size * 0.5
    painter.drawPolygon(QPolygonF([
        QPointF(cx - w / 2, cy - h / 2),
        QPointF(cx - w / 2, cy + h / 2),
        QPointF(cx + w / 2, cy),
    ]))

    painter.end()
    return image


def to_png(image: QImage) -> bytes:
    # The QByteArray must outlive the QBuffer that wraps it, so it is a named
    # local rather than a temporary.
    store = QByteArray()
    buffer = QBuffer(store)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, 'PNG')
    buffer.close()
    return bytes(store)


def build_ico(images: list[QImage]) -> bytes:
    """Pack PNG-compressed entries into an ICO container."""
    blobs = [to_png(img) for img in images]
    count = len(blobs)

    header = struct.pack('<HHH', 0, 1, count)
    offset = 6 + 16 * count

    entries, payload = b'', b''
    for image, blob in zip(images, blobs):
        side = 0 if image.width() >= 256 else image.width()
        entries += struct.pack(
            '<BBBBHHII', side, side, 0, 0, 1, 32, len(blob), offset,
        )
        payload += blob
        offset += len(blob)

    return header + entries + payload


def main() -> int:
    # Kept in a module-level name so Qt is not torn down while images live.
    global _app
    _app = QGuiApplication.instance() or QGuiApplication([])

    images = [draw(size) for size in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(images))
    print(f'wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KB, sizes {SIZES})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
