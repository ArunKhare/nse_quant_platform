"""Persistent kill switch."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class KillSwitch:
    def __init__(self,path:str|Path="data/kill_switch.json"): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
    def is_active(self)->bool:
        if not self.path.exists(): return False
        try: return bool(json.loads(self.path.read_text()).get("active",False))
        except (json.JSONDecodeError,OSError): return True
    def activate(self,reason:str="manual"): self.path.write_text(json.dumps({"active":True,"reason":reason,"ts":datetime.now(UTC).isoformat()},indent=2))
    def deactivate(self):
        if self.path.exists(): self.path.unlink()
