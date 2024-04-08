import os

from celery import Celery
from celery.exceptions import Reject

BROKER_URL = os.environ.get('BROKER_URL', 'amqp://guest:guest@localhost:8672')

app = Celery(
    broker=BROKER_URL,
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_enable_remote_control=True,
    task_default_exchange='service_a',
    task_default_queue='service_a',
    event_exchange='service_a.celeryev',
    event_queue_prefix='service_a.celeryev',
    control_exchange='service_a',
)


@app.task()
def test_succeeded():
    print('succeeded')


@app.task()
def test_failed():
    raise RuntimeError("Can't process task")


@app.task(acks_late=True)
def test_reject_with_no_requeue():
    raise Reject('Reject with no requeue', requeue=False)


@app.task(
    autoretry_for=(RuntimeError,),
    max_retries=4,
    retry_backoff=False,
    default_retry_delay=5,
)
def test_retried():
    raise RuntimeError("Can't process task")


@app.task()
def test_revoked():
    print("I won't be called")


if __name__ == '__main__':
    app.start()
