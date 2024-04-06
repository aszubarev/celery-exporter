from celery.events.state import State

events_state = State()

worker_last_seen: dict[tuple[str, str], float] = {}

queue_cache: dict[str, set[str]] = {}
