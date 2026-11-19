"""The active theme, exposed to QML as `Theme`.

Every color in the QML is bound to Theme.c.<key>, so changing a color here
repaints the whole window immediately. Edits are live but unsaved until
saveAs() is called; switching themes discards them.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QUrl, Property, Signal, Slot

from .. import settings, themes


class ThemeBridge(QObject):
    changed = Signal()
    listChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = themes.load(settings.get('theme'))
        self._dirty = False

    # -- current theme ----------------------------------------------------

    def _colors(self) -> dict:
        return dict(self._theme.colors)

    def _name(self) -> str:
        return self._theme.name

    def _radius(self) -> int:
        return self._theme.radius

    def _preset(self) -> bool:
        return self._theme.preset

    def _is_dirty(self) -> bool:
        return self._dirty

    c = Property('QVariantMap', _colors, notify=changed)
    name = Property(str, _name, notify=changed)
    radius = Property(int, _radius, notify=changed)
    preset = Property(bool, _preset, notify=changed)
    dirty = Property(bool, _is_dirty, notify=changed)

    @property
    def colors(self) -> dict:
        """Plain dict of the current colors, for the countdown window."""
        return dict(self._theme.colors)

    # -- listing ------------------------------------------------------------

    def _themes(self) -> list:
        return [
            {'name': t.name, 'preset': t.preset, 'colors': dict(t.colors)}
            for t in themes.list_themes()
        ]

    def _keys(self) -> list:
        return [{'key': k, 'label': themes.LABELS[k]} for k in themes.KEYS]

    all = Property('QVariantList', _themes, notify=listChanged)
    keys = Property('QVariantList', _keys, constant=True)

    # -- actions --------------------------------------------------------------

    @Slot(str)
    def apply(self, name: str) -> None:
        self._theme = themes.load(name)
        self._dirty = False
        settings.set_value('theme', self._theme.name)
        self.changed.emit()

    @Slot(str, str)
    def setColor(self, key: str, value: str) -> None:  # noqa: N802
        if key not in themes.KEYS:
            return
        fixed = themes.from_dict({'name': 'x', 'colors': {key: value}}).colors[key]
        if fixed != value.lower():
            return  # not a #rrggbb value yet; keep the old color while typing
        if self._theme.colors.get(key) != fixed:
            self._theme.colors[key] = fixed
            self._dirty = True
            self.changed.emit()

    @Slot(int)
    def setRadius(self, value: int) -> None:  # noqa: N802
        value = max(0, min(24, int(value)))
        if value != self._theme.radius:
            self._theme.radius = value
            self._dirty = True
            self.changed.emit()

    @Slot(str, result=str)
    def saveAs(self, name: str) -> str:  # noqa: N802
        """Save the current colors under a name. Returns an error or ''."""
        name = (name or '').strip()
        if not name:
            return 'Enter a name for the theme.'
        draft = themes.Theme(name=name, colors=dict(self._theme.colors), radius=self._theme.radius)
        try:
            self._theme = themes.save(draft)
        except themes.ThemeError as exc:
            return str(exc)
        self._dirty = False
        settings.set_value('theme', self._theme.name)
        self.listChanged.emit()
        self.changed.emit()
        return ''

    @Slot()
    def revert(self) -> None:
        self.apply(self._theme.name)

    @Slot(str, result=bool)
    def remove(self, name: str) -> bool:
        if not themes.delete(name):
            return False
        self.listChanged.emit()
        if name.lower() == self._theme.name.lower():
            self.apply(themes.DEFAULT)
        return True

    @Slot(QUrl, result=str)
    def importTheme(self, url: QUrl) -> str:  # noqa: N802
        try:
            theme = themes.import_file(url.toLocalFile())
        except themes.ThemeError as exc:
            return str(exc)
        self.listChanged.emit()
        self.apply(theme.name)
        return ''

    @Slot(QUrl, result=str)
    def exportTheme(self, url: QUrl) -> str:  # noqa: N802
        path = url.toLocalFile()
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            themes.export_file(self._theme, path)
        except themes.ThemeError as exc:
            return str(exc)
        return ''
