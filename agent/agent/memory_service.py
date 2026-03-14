import json

from agent.persistence.model import Conversation
from agent.types import AnthropicMessage


class MemoryService:
    def retrieve_conversation(self, hash_key: str, sort_key: int) -> list[AnthropicMessage]:
        conversation: Conversation = Conversation.select().where(
            Conversation.hash_key == hash_key,
            Conversation.sort_key == sort_key
        ).order_by(Conversation.created_at.desc()).get()
        return json.loads(conversation.content)

    def save_conversation(self, hash_key: str, sort_key: int, messages: list[AnthropicMessage]):
        conversation: Conversation = Conversation.create(
            hash_key=hash_key,
            sort_key=sort_key,
            content=json.dumps(messages)
        )
        conversation.save()
