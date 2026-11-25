"""Install new files only from the reviewed baseline; no charter or runner edits."""

import hashlib
import shutil
import subprocess
from pathlib import Path

BASELINE = "1467cc8d8b4630fe2cad61181c6d10a03a06a7ae"
root = Path(__file__).resolve().parents[1]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
if head != BASELINE:
    raise SystemExit(f"Expected HEAD {BASELINE}; got {head}. Compare sources before applying.")
if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip():
    raise SystemExit("Tracked checkout changes present; review them before applying.")
expected = {
    "src/nse_quant/data_platform/audit.py": "f33749f7b00e8ce4c30f0f3f241f588b916199d4",
    "src/nse_quant/data_platform/contracts.py": "df169cb82ead1ba9d01ad2d8a734070d9cde5c24",
    "src/nse_quant/analytics/s2_iv30_history.py": "9fcdb54444868dff87ce1cb4874247dcdb610d03",
    "src/nse_quant/data_platform/s2_vix_minute_bars.py": "551594ead877f534ccb257cff8904ff08ef1a3b7",
}
for name, pin in expected.items():
    # Git reads the committed bytes, so Windows checkout newline conversion is harmless.
    raw = subprocess.check_output(["git", "show", f"HEAD:{name}"])
    digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if digest != pin:
        raise SystemExit(f"Baseline dependency differs: {name}; no writes performed")
sources = [p for folder in ("src", "tests", "docs/s2") for p in (root / folder).rglob("*") if p.is_file()]
for source in sources:
    target = Path(source.relative_to(root))
    if target.exists() and target.read_bytes() != source.read_bytes():
        raise SystemExit(f"Refusing overwrite: {target}; no writes performed")
for source in sources:
    target = Path(source.relative_to(root))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.resolve() != source.resolve():
        shutil.copyfile(source, target)
print("Installed S2 series candidate files only. Review git diff; run checkout tests.")
