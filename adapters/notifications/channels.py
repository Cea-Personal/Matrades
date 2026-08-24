from typing import Protocol


class NotificationChannel(Protocol):
    async def send(self, destination: str, title: str, body: str) -> str: ...


class RecordingChannel:
    def __init__(self, name: str):
        self.name = name
        self.sent = []

    async def send(self, destination: str, title: str, body: str) -> str:
        delivery_id = f"{self.name}-{len(self.sent) + 1}"
        self.sent.append((delivery_id, destination, title, body))
        return delivery_id


def channels():
    return {name: RecordingChannel(name) for name in ("email", "telegram", "browser_push")}
