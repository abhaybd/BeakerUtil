from functools import wraps
from beaker import Beaker

def inject_beaker(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with Beaker.from_env() as beaker:
            return func(beaker, *args, **kwargs)
    return wrapper

def get_workloads_and_jobs(beaker: Beaker):
    workloads = list(beaker.workload.list(author=beaker.user_name, finalized=False))
    jobs = [beaker.workload.get_latest_job(w) for w in workloads]
    workloads = [w for w, j in zip(workloads, jobs) if j is not None]
    jobs = [j for j in jobs if j is not None]
    return workloads, jobs
