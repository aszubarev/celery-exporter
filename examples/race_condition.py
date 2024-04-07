from celery.events.state import State, Task

task_sent_event = {
  "hostname": "gen7460@aszubarev-mac.local",
  "utcoffset": -3,
  "pid": 7460,
  "clock": 6,
  "uuid": "4e71454e-e0bf-477c-8abf-9559721de49d",
  "root_id": "4e71454e-e0bf-477c-8abf-9559721de49d",
  "parent_id": None,
  "name": "tasks.foo",
  "args": "()",
  "kwargs": "{}",
  "retries": 0,
  "eta": None,
  "expires": None,
  "queue": "celery",
  "exchange": "",
  "routing_key": "celery",
  "timestamp": 1712401950.239082,
  "type": "task-sent",
  "local_received": 1712401950.245164
}
task_received_event = {
  "hostname": "celery@aszubarev-mac.local",
  "utcoffset": -3,
  "pid": 7226,
  "clock": 6,
  "uuid": "4e71454e-e0bf-477c-8abf-9559721de49d",
  "name": "tasks.foo",
  "args": "()",
  "kwargs": "{}",
  "root_id": "4e71454e-e0bf-477c-8abf-9559721de49d",
  "parent_id": None,
  "retries": 0,
  "eta": None,
  "expires": None,
  "timestamp": 1712401950.2415,
  "type": "task-received",
  "local_received": 1712401950.244245
}

state = State()

state.event(task_received_event)
state.event(task_sent_event)

task: Task = state.tasks.get("4e71454e-e0bf-477c-8abf-9559721de49d")

print(task.state)  # RECEIVED
