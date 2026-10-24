import hashlib
from pathlib import Path


def version():
    root=Path(__file__).resolve().parent
    digest=hashlib.sha256()
    files=list(root.glob('*.py'))+list((root/'templates').glob('*.html'))+list((root/'static').glob('*'))
    for p in sorted(files):
        if p.is_file():digest.update(p.name.encode());digest.update(p.read_bytes())
    return digest.hexdigest()[:16]
