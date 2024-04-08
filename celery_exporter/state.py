from collections import defaultdict

from celery.events.state import State

events_state = State()

worker_last_seen: dict[tuple[str, str], float] = {}

queues: dict[str, set[str]] = defaultdict(set)
