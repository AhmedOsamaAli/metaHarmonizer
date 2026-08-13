from app.core.settings import settings
from app.workers.arq_worker import WorkerSettings


def test_worker_uses_measured_ml_concurrency_default():
    assert settings.worker_max_jobs == 2
    assert WorkerSettings.max_jobs == settings.worker_max_jobs