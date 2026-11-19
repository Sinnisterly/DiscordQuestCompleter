"""Check theme loading, saving and fallback behaviour."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dqc import themes  # noqa: E402

failures = []

presets = [t for t in themes.list_themes() if t.preset]
print(f'presets: {[t.name for t in presets]}')
if not presets or presets[0].name != themes.DEFAULT:
    failures.append('Midnight should be listed first')
for theme in presets:
    if set(theme.colors) != set(themes.KEYS):
        failures.append(f'{theme.name} is missing colors')

# Round trip a user theme.
name = 'Check Theme 7f3a'
custom = themes.load('Midnight')
custom.name = name
custom.colors['accent'] = '#ff00aa'
themes.save(custom)
again = themes.load(name)
if again.colors['accent'] != '#ff00aa' or again.preset:
    failures.append('saved theme did not load back')
if not themes.delete(name) or themes.load(name).name != themes.DEFAULT:
    failures.append('delete did not remove the theme')

# Presets are protected.
try:
    themes.save(themes.Theme(name='Midnight'))
    failures.append('saving over a preset should fail')
except themes.ThemeError:
    pass
if themes.delete('Midnight'):
    failures.append('deleting a preset should fail')

# Bad values fall back instead of failing.
broken = themes.from_dict({'name': 'Broken', 'colors': {'bg': 'red', 'text': '#FFFFFF'}, 'radius': 99})
if broken.colors['bg'] != '#15171d' or broken.colors['text'] != '#ffffff' or broken.radius != 10:
    failures.append(f'fallback wrong: {broken}')

# Import gives a preset-named file a new name.
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'shared.json'
    path.write_text(json.dumps({'name': 'Light', 'colors': {}}), encoding='utf-8')
    imported = themes.import_file(path)
    if imported.name != 'Light (imported)':
        failures.append(f'import name: {imported.name}')
    themes.delete(imported.name)

print('\nFAIL\n' + '\n'.join(failures) if failures else '\nOK')
sys.exit(1 if failures else 0)
