import logging
import random
from threading import Thread
from time import sleep

import service_a
import service_default
from celery.result import AsyncResult

apps = {
    'default': service_default.app,
    'service_a': service_a.app,
}


tasks = {
    'default': {
        1: service_default.test_succeeded_1,
        2: service_default.test_succeeded_2,
        3: service_default.test_succeeded_3,
        4: service_default.test_succeeded_4,
        5: service_default.test_succeeded_5,
        6: service_default.test_succeeded_1,
        7: service_default.test_succeeded_2,
        8: service_default.test_succeeded_3,
        9: service_default.test_succeeded_4,
        10: service_default.test_succeeded_5,
        11: service_default.test_failed_1,
        12: service_default.test_failed_2,
        13: service_default.test_failed_3,
        14: service_default.test_succeeded_1,
        15: service_default.test_succeeded_2,
        16: service_default.test_succeeded_1,
        17: service_default.test_succeeded_2,
        18: service_default.test_succeeded_1,
        19: service_default.test_succeeded_1,
        20: service_default.test_succeeded_1,
        21: service_default.test_reject_with_no_requeue,
        22: service_default.test_reject_with_no_requeue,
        23: service_default.test_reject_with_no_requeue,
        24: service_default.test_retried,
    },
    'service_a': {
        1: service_a.test_failed_1,
        2: service_a.test_failed_2,
        3: service_a.test_failed_3,
        4: service_a.test_succeeded_4,
        5: service_a.test_succeeded_5,
        6: service_a.test_succeeded_1,
        7: service_a.test_succeeded_2,
        8: service_a.test_succeeded_3,
        9: service_a.test_succeeded_4,
        10: service_a.test_succeeded_5,
        11: service_a.test_failed_1,
        12: service_a.test_failed_2,
        13: service_a.test_failed_3,
        14: service_a.test_failed_1,
        15: service_a.test_failed_2,
        16: service_a.test_failed_3,
        17: service_a.test_retried,
        18: service_a.test_retried,
        19: service_a.test_retried,
        20: service_a.test_retried,
        21: service_a.test_reject_with_no_requeue,
        22: service_a.test_reject_with_no_requeue,
        23: service_a.test_reject_with_no_requeue,
        24: service_a.test_reject_with_no_requeue,
    },
}


class Producer:

    def run(self):
        Thread(target=self.run_tasks, args=('default',)).start()
        Thread(target=self.run_tasks, args=('service_a',)).start()

    @classmethod
    def run_tasks(cls, service_name) -> None:

        while True:
            task_idx = random.choice(tuple(tasks[service_name].keys()))

            task = tasks[service_name][task_idx]

            countdown = None
            need_revoke = cls._need_revoke()
            if need_revoke:
                countdown = 10

            try:
                result: AsyncResult = task.apply_async(countdown=countdown)
            except Exception:
                logging.exception("Can't apply async")
            else:
                if need_revoke:
                    try:
                        apps[service_name].control.revoke(result.id)
                    except Exception:
                        logging.exception("Can't revoke")

            timeout = random.uniform(0.1, 1)

            sleep(timeout)

    @classmethod
    def _need_revoke(cls):
        chance = random.randint(0, 100)
        return chance % 10 == 0


producer = Producer()


if __name__ == '__main__':
    producer.run()
