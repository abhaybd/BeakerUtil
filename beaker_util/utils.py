from functools import wraps
from typing import Any
import re

from beaker import Beaker, BeakerJob
import yaml


class ConfigDumper(yaml.SafeDumper):
    """
    Custom YAML dumper to insert blank lines between top-level objects.
    See: https://github.com/yaml/pyyaml/issues/127#issuecomment-525800484
    """

    def write_line_break(self, data=None):
        super().write_line_break(data)
        if len(self.indents) == 1:
            super().write_line_break()


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


def get_jobs_and_nodes(beaker: Beaker):
    interactive_jobs: list[BeakerJob] = []
    noninteractive_jobs: list[BeakerJob] = []
    for workload in beaker.workload.list(author=beaker.user_name, finalized=False):
        job = beaker.workload.get_latest_job(workload)
        if job is not None:
            if beaker.workload.is_environment(workload):
                interactive_jobs.append(job)
            elif beaker.workload.is_experiment(workload):
                noninteractive_jobs.append(job)

    interactive = [(j, beaker.node.get(j.assignment_details.node_id)) for j in interactive_jobs]
    noninteractive = [(j, beaker.node.get(j.assignment_details.node_id)) for j in noninteractive_jobs]

    interactive.sort(key=lambda x: x[1].hostname + x[0].id)
    noninteractive.sort(key=lambda x: x[1].hostname + x[0].id)
    return interactive, noninteractive


def find_clusters(beaker: Beaker, pattern: str):
    clusters = beaker.cluster.list()
    return [c for c in clusters if re.match(pattern, f"{c.organization_name}/{c.name}")]


def merge_configs(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    ret = deepcopy(a)
    for k, v in b.items():
        if k in ret:
            if isinstance(ret[k], dict) and isinstance(v, dict):
                ret[k] = merge_configs(ret[k], v)
            elif isinstance(ret[k], list) and isinstance(v, list):
                ret[k] = ret[k] + v
            else:
                ret[k] = v
        else:
            ret[k] = v
    return ret
