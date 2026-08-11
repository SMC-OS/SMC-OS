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
        print(repr(agent))

        if agent == "sales":
            return self.sales.reply(db, text)

        if agent == "search":
            return self.search.search(db, text)

        return {
            "agent": agent,
            "request": text,
            "status": "received"
        }