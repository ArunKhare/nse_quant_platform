"""Telegram notifier."""
from __future__ import annotations
import os,requests

class Notifier:
    def __init__(self,token:str|None=None,chat_id:str|None=None):
        self.token=token or os.getenv("TELEGRAM_BOT_TOKEN"); self.chat_id=chat_id or os.getenv("TELEGRAM_CHAT_ID")
    def send(self,msg:str)->bool:
        if not self.token or not self.chat_id: return False
        try: return requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",json={"chat_id":self.chat_id,"text":msg},timeout=10).ok
        except requests.RequestException: return False
