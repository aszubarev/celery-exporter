from time import sleep

import service_a as tasks
from celery.result import AsyncResult

tasks.test_succeeded.delay()
tasks.test_failed.delay()
tasks.test_reject_with_no_requeue.delay()
tasks.test_retried.delay()

result: AsyncResult = tasks.test_revoked.apply_async(countdown=5)
print(result.id)
sleep(1)
print(f'{result.id} revoke')
tasks.app.control.revoke(result.id)

