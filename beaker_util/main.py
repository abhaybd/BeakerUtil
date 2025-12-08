from argparse import ArgumentParser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
from copy import deepcopy
from datetime import datetime
import os
import re
import sys
import warnings
warnings.filterwarnings("ignore", module="beaker")

import yaml
from tabulate import tabulate
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from beaker import Beaker, BeakerJob, BeakerNode, BeakerWorkloadStatus, BeakerCluster

from beaker_util.monitor import monitor
from beaker_util.utils import ConfigDumper, find_clusters, get_jobs_and_nodes, get_workloads_and_jobs, inject_beaker, merge_configs


CONF_DIR = os.path.join(os.environ["HOME"], ".beakerutil")
LAUNCH_CONF_PATH = os.path.abspath(os.path.join(CONF_DIR, "launch.conf"))
DEFAULT_LAUNCH_CONFIG = "DEFAULT"


@inject_beaker
def list_sessions(beaker: Beaker, _, __):
    workloads, _ = get_workloads_and_jobs(beaker)

    idx = 0

    def print_sessions(title, s: list[tuple[BeakerJob, BeakerNode | None]]):
        nonlocal idx
        if len(s) == 0:
            return
        print(title)
        for j, n in s:
            name_str = f" (name={j.name})" if j.name else ""
            reserved_str = "with no resources requested"
            if j.assignment_details.HasField("resource_assignment"):
                reserved_str = f"using: [{len(j.assignment_details.resource_assignment.gpus)} GPU(s)"
                if j.assignment_details.resource_assignment.memory_bytes:
                    reserved_str += f", {j.assignment_details.resource_assignment.memory_bytes} of memory"
                if j.assignment_details.resource_assignment.cpu_count:
                    reserved_str += f", {j.assignment_details.resource_assignment.cpu_count:g} CPU(s)"
                reserved_str += "]"

            job_created = datetime.fromtimestamp(j.status.created.seconds + j.status.created.nanos / 1e9)
            now = datetime.now(job_created.tzinfo)
            job_duration = now - job_created
            days = job_duration.days
            hours = job_duration.seconds // 3600
            minutes = (job_duration.seconds % 3600) // 60
            if days > 0:
                duration_str = f"{days} days"
            elif hours > 0:
                duration_str = f"{hours} hours"
            elif minutes > 0:
                duration_str = f"{minutes} minute{'' if minutes == 1 else 's'}"
            else:
                duration_str = "less than a minute"

            node_str = f"on node {n.hostname}" if n is not None else "waiting for assignment"
            print(f"\t{idx}: Session {j.id}{name_str} {node_str} {reserved_str}, status={BeakerWorkloadStatus(j.status.status).name}, running for {duration_str}")
            idx += 1

    if len(workloads):
        inter, noninter = get_jobs_and_nodes(beaker)
        print_sessions("Interactive sessions:", inter)
        print_sessions("Noninteractive sessions:", noninter)
    else:
        print(f"No sessions found for author {beaker.user_name}.")


@inject_beaker
def attach(beaker: Beaker, args, _):
    workloads, jobs = get_workloads_and_jobs(beaker)
    session_idxs = [i for i, w in enumerate(workloads) if beaker.workload.is_environment(w)]
    session_workloads = [workloads[i] for i in session_idxs]
    session_jobs = [jobs[i] for i in session_idxs]

    assert isinstance(args.session_idx, (type(None), int))
    if len(session_workloads) == 0:
        print(f"No sessions found for author {beaker.user_name}.")
        exit(1)
    elif args.session_idx is not None:
        if args.session_idx < 0 or args.session_idx >= len(session_workloads):
            print(f"Invalid session index {args.session_idx}!")
            exit(1)
        inter, _ = get_jobs_and_nodes(beaker)
        if args.session_idx < len(inter):
            session, _ = inter[args.session_idx]
        else:
            assert False, "This should never happen! session_idx < len(session_workloads) but session_idx >= len(inter)"
    elif args.name is not None:
        session = next((s for s in session_jobs if s.name == args.name), None)
        if session is None:
            print(f"No session found with name {args.name}!")
            exit(1)
    elif args.id is not None:
        session = next((s for s in session_jobs if s.id == args.id), None)
        if session is None:
            print(f"No session found with id {args.id}!")
            exit(1)
    elif len(session_jobs) == 1:
        session = session_jobs[0]
    else:
        print("No session specified and no unique session found!")
        exit(1)
    node = beaker.node.get(session.assignment_details.node_id)
    print(f"Attempting to attach to session {session.name or session.id} on node {node.hostname}...")
    os.execlp("beaker", *f"beaker session attach --remote {session.id}".split())


@inject_beaker
def launch_interactive(beaker: Beaker, args, extra_args: list[str]):
    try:
        with open(LAUNCH_CONF_PATH, "r") as f:
            conf: dict[str, dict[str, str]] = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"No launch configuration found at {LAUNCH_CONF_PATH}! Create one to use this command.")
        exit(1)

    if args.launch_config not in conf:
        print(f"No launch configuration found for {args.launch_config}!")
        exit(1)

    launch_conf = merge_configs(conf[args.launch_config], conf.get(DEFAULT_LAUNCH_CONFIG, {}))

    clusters = find_clusters(beaker, launch_conf["cluster"])
    if len(clusters) == 0:
        print(f"No clusters found for pattern {launch_conf['cluster']}!")
        exit(1)

    beaker_cmd = f"beaker session create -w {launch_conf['workspace']} --budget {launch_conf['budget']} --remote --bare"
    for cluster in clusters:
        beaker_cmd += f" --cluster {cluster.organization_name}/{cluster.name}"
    for mount in launch_conf.get("mounts", []):
        beaker_cmd += f" --mount src={mount['src']},ref={mount['ref']},dst={mount['dst']}"
    for env, secret in launch_conf.get("env_secrets", {}).items():
        beaker_cmd += f" --secret-env {env}={secret}"
    if "gpus" in launch_conf:
        beaker_cmd += f" --gpus {launch_conf['gpus']}"
    if "port" in launch_conf:
        beaker_cmd += f" --port {launch_conf['port']}"

    if len(extra_args) > 0:
        beaker_cmd += f" {' '.join(extra_args)}"

    if args.dry_run:
        print("Would execute:")
        print(beaker_cmd)
    else:
        print(*beaker_cmd.split())
        os.execlp("beaker", *beaker_cmd.split())


def view_config(args, _):
    if args.config_type == "launch":
        with open(LAUNCH_CONF_PATH, "r") as f:
            launch_conf: dict[str, dict] = yaml.safe_load(f)
        default_conf = launch_conf.pop(DEFAULT_LAUNCH_CONFIG, {})
        for conf in launch_conf.values():
            conf.update(deepcopy(default_conf))
        print(yaml.dump(launch_conf, indent=4, Dumper=ConfigDumper))
    else:
        raise ValueError(f"Unknown configuration type: {args.config_type}")


@inject_beaker
def stop(beaker: Beaker, args, _):
    workloads, jobs = get_workloads_and_jobs(beaker)
    assert isinstance(args.session_idx, (type(None), int))

    if len(workloads) == 0:
        print(f"No workloads found for author {beaker.user_name}.")
        exit(1)
    elif args.session_idx is not None:
        if args.session_idx < 0 or args.session_idx >= len(workloads):
            print(f"Invalid workload index {args.session_idx}!")
            exit(1)
        inter, noninter = get_jobs_and_nodes(beaker)
        if args.session_idx < len(inter):
            job, _ = inter[args.session_idx]
        else:
            job, _ = noninter[args.session_idx - len(inter)]
    elif args.name is not None:
        job = next((j for j in jobs if j.name == args.name), None)
        if job is None:
            print(f"No job found with name {args.name}!")
            exit(1)
    elif args.id is not None:
        job = next((j for j in jobs if j.id == args.id), None)
        if job is None:
            print(f"No job found with id {args.id}!")
            exit(1)
    elif len(jobs) == 1:
        job = jobs[0]
    else:
        print("No session specified and no unique session found!")
        exit(1)

    node = beaker.node.get(job.assignment_details.node_id)
    workload = beaker.workload.get(job.workload_id)
    is_interactive = beaker.workload.is_environment(workload)
    print(f"Attempting to stop {'interactive' if is_interactive else 'noninteractive'} session {job.name or job.id} on node {node.hostname}...")
    if is_interactive:
        os.execlp("beaker", *f"beaker session stop {job.id}".split())
    else:
        os.execlp("beaker", *f"beaker job cancel {job.id}".split())


@inject_beaker
def clusters(beaker: Beaker, args, _):
    @inject_beaker
    def get_cluster_info(b: Beaker, cluster: BeakerCluster):
        n_gpu, n_used_gpu = 0, 0
        node_free_gpus = defaultdict(int)
        for node in list(b.node.list(cluster=cluster)):
            if len(node.node_resources.gpu_ids) == 0:
                continue
            n_gpu += len(node.node_resources.gpu_ids)
            node_used_gpu = 0
            for job in b.job.list(scheduled_on_node=node, finalized=False):
                if job.assignment_details.HasField("resource_assignment"):
                    node_used_gpu += len(job.assignment_details.resource_assignment.gpus)
            n_used_gpu += node_used_gpu
            node_free_gpus[len(node.node_resources.gpu_ids) - node_used_gpu] += 1
        return {
            "name": cluster.name,
            "used_gpus": n_used_gpu,
            "gpus": n_gpu,
            "node_gpu_availability": {**node_free_gpus},
        }

    with ThreadPoolExecutor(args.n_workers) as executor:
        futures: list[Future[dict]] = []
        for cluster in beaker.cluster.list(sort_field=args.sort):
            if not args.filter or re.match(args.filter, cluster.name):
                futures.append(executor.submit(get_cluster_info, cluster))

        rows = []
        for future in futures:
            cluster_info = future.result()
            if args.all or cluster_info['gpus'] > 0:
                row = []
                row.append(cluster_info['name'])
                row.append(cluster_info['used_gpus'])
                row.append(cluster_info['gpus'])
                if args.print_node_availability and cluster_info['gpus'] > 0:
                    node_free_gpus = cluster_info['node_gpu_availability']
                    availability_str = "{" + ", ".join(f"{i}: {node_free_gpus.get(i, 0)}" for i in range(max(node_free_gpus.keys()) + 1)) + "}"
                    row.append(availability_str)
                #     print(f"\tNode Availability by # of GPUs: {availability_str}")
                rows.append(row)
        
        headers = ["Cluster", "Used GPUs", "Total GPUs"]
        if args.print_node_availability:
            headers.append("Node Availability")
        print(tabulate(rows, headers=headers))


def get_args(argv):
    parser = ArgumentParser(prog="beakerutil", description="Collection of utilities for Beaker", allow_abbrev=False)
    subparsers = parser.add_subparsers(required=True, dest="command")

    launch_parser = subparsers.add_parser("launch", help="Launch interactive session on any available node in a cluster.", allow_abbrev=False)
    if os.path.isfile(LAUNCH_CONF_PATH):
        with open(LAUNCH_CONF_PATH, "r") as f:
            launch_conf: dict[str, dict] = yaml.safe_load(f)
        available_launch_configs = sorted(launch_conf.keys() - {DEFAULT_LAUNCH_CONFIG})
    else:
        available_launch_configs = []
    launch_parser.add_argument("launch_config", help="The launch configuration to use.", choices=available_launch_configs)
    launch_parser.add_argument("--dry-run", action="store_true", help="Print the command that would be executed without running it")
    launch_parser.set_defaults(func=launch_interactive)

    list_parser = subparsers.add_parser("list", help="List all sessions", allow_abbrev=False)
    list_parser.set_defaults(func=list_sessions)

    monitor_parser = subparsers.add_parser("monitor", help="Monitor the resource usage of running experiments", allow_abbrev=False)
    monitor_exc_group = monitor_parser.add_mutually_exclusive_group(required=False)
    monitor_exc_group.add_argument("-n", "--interval", type=int, default=2, help="The interval in seconds between updates")
    monitor_exc_group.add_argument("--once", action="store_true", help="Run once and exit instead of continuously updating")
    monitor_parser.set_defaults(func=monitor)

    attach_parser = subparsers.add_parser("attach", help="Attach to a running session", allow_abbrev=False)
    attach_group = attach_parser.add_mutually_exclusive_group(required=False)
    attach_group.add_argument("-n", "--name", help="The name of the session to attach to")
    attach_group.add_argument("-i", "--id", help="The id of the session to attach to")
    attach_group.add_argument("session_idx", type=int, nargs="?", help="The index of the session to attach to")
    attach_parser.set_defaults(func=attach)

    config_parser = subparsers.add_parser("config", help="View configuration", allow_abbrev=False)
    config_parser.add_argument("config_type", help="The type of configuration to view", choices=["launch"])
    config_parser.set_defaults(func=view_config)

    stop_parser = subparsers.add_parser("stop", help="Stop a running session", allow_abbrev=False)
    stop_group = stop_parser.add_mutually_exclusive_group(required=False)
    stop_group.add_argument("-n", "--name", help="The name of the session to stop")
    stop_group.add_argument("-i", "--id", help="The id of the session to stop")
    stop_group.add_argument("session_idx", type=int, nargs="?", help="The index of the session to stop")
    stop_parser.set_defaults(func=stop)

    clusters_parser = subparsers.add_parser("clusters", help="List all clusters", allow_abbrev=False)
    clusters_parser.add_argument("--sort", choices=["name", "total_gpus", "free_gpus"], default="total_gpus",
        help="The field to sort by, defaults to total GPUs")
    clusters_parser.add_argument("--all", help="Show all clusters, not just those with GPUs")
    clusters_parser.add_argument("--print-node-availability", action="store_true")
    clusters_parser.add_argument("--filter", default="(?!ai1)", nargs="?",
        help="Regex specifying clusters to display. Defaults to everything except ai1 clusters.")
    clusters_parser.add_argument("--n-workers", type=int, default=8,
        help="Number of threads to use to fetch cluster information")
    clusters_parser.set_defaults(func=clusters)

    args, extra_args = parser.parse_known_args(argv)
    if len(extra_args) > 0 and extra_args[0] == "--":
        extra_args = extra_args[1:]

    return args, extra_args


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    args, extra_args = get_args(argv)
    args.func(args, extra_args)


if __name__ == "__main__":
    main()
