import os
import random
from time import sleep

import kombu
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
    task_queues=[
        kombu.Queue(name='service_a.default', routing_key='default'),
        kombu.Queue(name='service_a.example_queue_1', routing_key='service_a.example_queue_1'),
        kombu.Queue(name='service_a.example_queue_2', routing_key='service_a.example_queue_2'),
        kombu.Queue(name='service_a.example_queue_3', routing_key='service_a.example_queue_3'),
    ],
    task_routes={
        '*test_succeeded_*': {'queue': 'service_a.example_queue_1'},
        '*test_failed_*': {'queue': 'service_a.example_queue_2'},
        '*test_retried': {'queue': 'service_a.example_queue_3'},
    },
)


@app.task()
def test_succeeded_1():
    sleep(random.uniform(0.2, 2))
    print('succeeded 1')


@app.task()
def test_succeeded_2():
    sleep(random.uniform(0.4, 4))
    print('succeeded 2')


@app.task()
def test_succeeded_3():
    sleep(random.uniform(0.6, 6))
    print('succeeded 3')


@app.task()
def test_succeeded_4():
    sleep(random.uniform(0.8, 8))
    print('succeeded 4')


@app.task()
def test_succeeded_5():
    sleep(random.uniform(1, 10))
    print('succeeded 5')


test_failed_exception_classes = {
    1: RuntimeError,
    2: ValueError,
    3: IndexError,
    4: ZeroDivisionError,
    5: NotImplementedError,
}


@app.task()
def test_failed_1():
    sleep(random.uniform(0.1, 1))
    exception_class_idx = random.choice((1, 2, 3))
    exception_class = test_failed_exception_classes[exception_class_idx]
    raise exception_class(f"Can't process task with random number {random.randint(1, 100)}")


@app.task()
def test_failed_2():
    sleep(random.uniform(0.5, 2))
    exception_class_idx = random.choice((2, 4, 5))
    exception_class = test_failed_exception_classes[exception_class_idx]
    raise exception_class(f"Can't process task with random number {random.randint(1, 100)}")


@app.task()
def test_failed_3():
    sleep(random.uniform(1, 5))
    exception_class_idx = random.choice((1, 3, 5))
    exception_class = test_failed_exception_classes[exception_class_idx]
    raise exception_class(f"Can't process task with random number {random.randint(1, 100)}")


@app.task(acks_late=True)
def test_reject_with_no_requeue():
    raise Reject('Reject with no requeue', requeue=False)


@app.task(
    autoretry_for=(RuntimeError,),
    max_retries=4,
    retry_backoff=False,
    default_retry_delay=1,
)
def test_retried():
    raise RuntimeError("Can't process task")


@app.task()
def test_revoked():
    print("I won't be called")


if __name__ == '__main__':
    app.start()
