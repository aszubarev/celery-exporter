import os

from celery import Celery

BROKER_URL = os.environ.get('BROKER_URL', 'amqp://guest:guest@localhost:8672')

app = Celery(
    broker=BROKER_URL,
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_enable_remote_control=True,
    task_default_exchange='service_b',
    task_default_queue='service_b',
    event_exchange='service_b.celeryev',
    event_queue_prefix='service_b.celeryev',
    control_exchange='service_b',
)


@app.task()
def test_succeeded():
    print('succeeded')


if __name__ == '__main__':
    app.start()
