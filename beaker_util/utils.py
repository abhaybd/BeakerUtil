from copy import deepcopy
from functools import wraps
from typing import Any
import re
from functools import cmp_to_key

from beaker import Beaker, BeakerJob, BeakerNode
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

    def get_node(j: BeakerJob):
        return beaker.node.get(j.assignment_details.node_id) if j.assignment_details.node_id else None

    interactive = [(j, get_node(j)) for j in interactive_jobs]
    noninteractive = [(j, get_node(j)) for j in noninteractive_jobs]

    def cmp(x1: tuple[BeakerJob, BeakerNode | None], x2: tuple[BeakerJob, BeakerNode | None]):
        # group jobs by node and sort by ID within each group (queued jobs go last)
        if x1[1] is None and x2[1] is not None:
            return 1
        elif x1[1] is not None and x2[1] is None:
            return -1
        elif x1[1] is None and x2[1] is None:
            return -1 if x1[0].id < x2[0].id else 1
        else:
            return -1 if x1[1].hostname + x1[0].id < x2[1].hostname + x2[0].id else 1

    interactive.sort(key=cmp_to_key(cmp))
    noninteractive.sort(key=cmp_to_key(cmp))
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
