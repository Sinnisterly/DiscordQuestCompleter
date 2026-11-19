"""Game artwork for QML, loaded off the UI thread.

QML asks for image://art/<game id>/S (row capsule) or /L (large header).
Downloads run on a small thread pool and use the disk cache in thumbs.py.
"""

from __future__ import annotations

from PySide6.QtCore import QRunnable, QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtQuick import (
    QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory,
)

from .. import thumbs
from ..catalog import Catalog


class _Response(QQuickImageResponse):
    def __init__(self):
        super().__init__()
        self._image = QImage()

    def textureFactory(self):  # noqa: N802 - Qt naming
        return QQuickTextureFactory.textureFactoryForImage(self._image)

    def deliver(self, image: QImage) -> None:
        self._image = image
        self.finished.emit()


class _Job(QRunnable):
    def __init__(self, response: _Response, game, large: bool):
        super().__init__()
        self.response = response
        self.game = game
        self.large = large

    def run(self):
        image = QImage()
        if self.game is not None:
            data = thumbs.fetch_for(self.game, large=self.large)
            if data:
                image.loadFromData(data)
        self.response.deliver(image)


class ArtProvider(QQuickAsyncImageProvider):
    def __init__(self, catalog: Catalog):
        super().__init__()
        self.catalog = catalog
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(6)

    def requestImageResponse(self, image_id: str, requested_size):  # noqa: N802
        game_id, _, size = image_id.rpartition('/')
        response = _Response()
        self.pool.start(_Job(response, self.catalog.by_id(game_id), size == 'L'))
        return response

    def shutdown(self) -> None:
        self.pool.clear()
        self.pool.waitForDone(2000)
