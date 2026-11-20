from pymongo import DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now

TITLE_CHARS = 60
MAX_MESSAGES = 200  # teto por thread: mantém o documento longe do limite de 16 MB do Mongo
MAX_THREADS = 100


class ChatThreadsRepo:
    """Conversas do assistente: um documento por thread, com as interações (pergunta + resposta +
    passos do grafo) embutidas em `messages`. `session_id` é o mesmo id da memória do agente, então
    reabrir uma thread continua a conversa. `_id` = "{user_id}:{session_id}": cada admin só enxerga as suas."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["chat_threads"]

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    async def add_turn(
        self, user_id: str, session_id: str, *, question_id: str, question: str, answer: str, steps: list[dict]
    ) -> None:
        t = now()
        message = {"question_id": question_id, "question": question, "answer": answer, "steps": steps, "at": t}
        await self.col.update_one(
            {"_id": self._key(user_id, session_id), "user_id": user_id},
            {
                "$setOnInsert": {"session_id": session_id, "title": question[:TITLE_CHARS], "created_at": t},
                "$set": {"updated_at": t},
                "$push": {"messages": {"$each": [message], "$slice": -MAX_MESSAGES}},
            },
            upsert=True,
        )

    async def list(self, user_id: str) -> list[dict]:
        cursor = self.col.find({"user_id": user_id}, {"session_id": 1, "title": 1, "updated_at": 1}).sort(
            "updated_at", DESCENDING
        )
        return await cursor.to_list(MAX_THREADS)

    async def get(self, user_id: str, session_id: str) -> dict | None:
        return await self.col.find_one({"_id": self._key(user_id, session_id), "user_id": user_id})

    async def delete(self, user_id: str, session_id: str) -> bool:
        result = await self.col.delete_one({"_id": self._key(user_id, session_id), "user_id": user_id})
        return result.deleted_count == 1
