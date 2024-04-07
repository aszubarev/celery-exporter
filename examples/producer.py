from time import sleep

import service_default
from celery.result import AsyncResult

service_default.test_succeeded.delay()
service_default.test_failed.delay()
service_default.test_reject_with_no_requeue.delay()
service_default.test_retried.delay()

result: AsyncResult = service_default.test_revoked.apply_async(countdown=5)
print(result.id)
sleep(1)
print(f'{result.id} revoke')
service_default.app.control.revoke(result.id)

