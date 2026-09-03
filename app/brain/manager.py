from sqlalchemy.orm import Session

from app.brain.router import BrainRouter
from app.assistant.sales import SalesAssistant

from app.assistant.search import SearchAssistant

class BrainManager:

    def __init__(self):
        self.router = BrainRouter()
        self.sales = SalesAssistant()
        self.search = SearchAssistant()

    def process(self, db: Session, text: str):

        agent = self.router.think(text)

        if agent == "sales":
            return self.sales.reply(db, text)

        if agent == "search":
            return self.search.search(db, text)

        if agent == "executive":
            # No keyword matched, but the canonical retrieval service
            # (app/materials/search.py) may still recognise a real
            # product in the free text — deterministic catalogue lookup
            # takes priority over the generic fallback reply whenever it
            # actually finds something (Sprint 032, Workstream B).
            fallback = self.search.search(db, text)
            if fallback["status"] != "not_found":
                return fallback

        return {
            "agent": agent,
            "request": text,
            "status": "received"
        }