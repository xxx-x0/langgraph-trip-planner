"""Package only reviewed extension sources; no accounts, settings or build cache."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
files = ('manifest.json', 'background.js', 'app-bridge.js', 'reader.js', 'ticket-page.js', 'README.md')
target = root / 'frontend/public/ticket-assistant-extension.zip'
target.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(target, 'w') as archive:
    for name in files:
        info = ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        archive.writestr(info, (root / 'browser-extension' / name).read_bytes())
print(target)
