"""Single-writer ordinary-exception rollback, not a power-loss transaction."""
import os
from pathlib import Path


def publish(files):
    """Stage all bytes before replacing targets; restore old bytes on failure."""
    previous = {Path(p): Path(p).read_bytes() if Path(p).exists() else None for p in files}
    staged = {}
    try:
        for target, data in files.items():
            target = Path(target)
            part = target.with_name(target.name + '.part')
            part.write_bytes(data)
            staged[target] = part
        for target, part in staged.items():
            os.replace(part, target)
    except Exception:
        for target, data in previous.items():
            if data is None:
                target.unlink(missing_ok=True)
            else:
                restore = target.with_name(target.name + '.restore')
                restore.write_bytes(data)
                os.replace(restore, target)
        raise
    finally:
        for part in staged.values():
            part.unlink(missing_ok=True)
