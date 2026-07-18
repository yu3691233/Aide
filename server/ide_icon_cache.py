"""Extract and cache installed IDE executable icons for all AideLink clients."""

import hashlib
import os
import subprocess
from pathlib import Path


def cached_ide_icon(executable_path):
    path = Path(executable_path or "")
    if os.name != "nt" or not path.is_file():
        return None
    cache_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AideLink" / "ide-icons"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = path.stat()
    digest = hashlib.sha1(f"{path}|{stat.st_mtime_ns}|{stat.st_size}".encode("utf-8")).hexdigest()[:20]
    target = cache_dir / f"{digest}.png"
    if target.exists() and target.stat().st_size:
        return target
    env = os.environ.copy()
    env["AIDELINK_ICON_SOURCE"] = str(path)
    env["AIDELINK_ICON_TARGET"] = str(target)
    command = (
        "Add-Type -AssemblyName System.Drawing;"
        "$i=[System.Drawing.Icon]::ExtractAssociatedIcon($env:AIDELINK_ICON_SOURCE);"
        "if($i){$b=$i.ToBitmap();"
        "$b.Save($env:AIDELINK_ICON_TARGET,[System.Drawing.Imaging.ImageFormat]::Png);"
        "$b.Dispose();$i.Dispose()}"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return target if target.exists() and target.stat().st_size else None
