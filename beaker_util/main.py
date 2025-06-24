from argparse import ArgumentParser
from copy import deepcopy
import os
import re
import sys
import warnings

import yaml
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from beaker import Beaker, JobKind, Job, Node

CONF_DIR = os.path.join(os.environ["HOME"], ".beakerutil")
LAUNCH_CONF_PATH = os.path.abspath(os.path.join(CONF_DIR, "launch.conf"))
DEFAULT_LAUNCH_CONFIG = "DEFAULT"


def requote(s: str):
    return s.replace("\\", "\\\\").replace('"', "\\\"")


def get_sessions_and_nodes(beaker: Beaker):
    sessions = beaker.job.list(author=beaker.account.whoami().name)
    interactive = [(j, beaker.node.get(j.node)) for j in sessions if j.kind == JobKind.session]
    noninteractive = [(j, beaker.node.get(j.node)) for j in sessions if j.kind == JobKind.execution]
    interactive.sort(key=lambda x: x[1].hostname + x[0].id)
    noninteractive.sort(key=lambda x: x[1].hostname + x[0].id)
    return interactive, noninteractive


def find_clusters(beaker: Beaker, pattern: str):
    clusters = beaker.cluster.list()
    return [c for c in clusters if re.match(pattern, c.name)]


def list_sessions(_, __):
    beaker = Beaker.from_env()
    sessions = beaker.job.list(author=beaker.account.whoami().name)

    idx = 0
    def print_sessions(title, s: list[tuple[Job, Node]]):
        nonlocal idx
        if len(s) == 0:
            return
        print(title)
        for j, n in s:
            name_str = f" (name={j.name})" if j.name else ""
            reserved_str = "with no resources reserved"
            if j.limits is not None:
                reserved_str = f"using: [{len(j.limits.gpus)} GPU(s)"
                if j.limits.memory:
                    reserved_str += f", {j.limits.memory} of memory"
                if j.limits.cpu_count:
                    reserved_str += f", {j.limits.cpu_count:g} CPU(s)"
                reserved_str += "]"

            print(f"\t{idx}: Session {j.id}{name_str} on node {n.hostname} {reserved_str}, status={j.status.current}")
            idx += 1

    if len(sessions):
        inter, noninter = get_sessions_and_nodes(beaker)
        print_sessions("Interactive sessions:", inter)
        print_sessions("Noninteractive sessions:", noninter)
    else:
        print(f"No sessions found for author {beaker.account.whoami().name}.")


def attach(args, _):
    beaker = Beaker.from_env()
    sessions = beaker.job.list(author=beaker.account.whoami().name)
    if len(sessions) == 0:
        print(f"No sessions found for author {beaker.account.whoami().name}.")
        exit(1)
    elif args.session_idx is not None:
        if args.session_idx < 0 or args.session_idx >= len(sessions):
            print(f"Invalid session index {args.session_idx}!")
            exit(1)
        inter, noninter = get_sessions_and_nodes(beaker)
        if args.session_idx < len(inter):
            session, _ = inter[args.session_idx]
        else:
            session, _ = noninter[args.session_idx - len(inter)]
    elif args.name is not None:
        session = next((s for s in sessions if s.name == args.name), None)
        if session is None:
            print(f"No session found with name {args.name}!")
            exit(1)
    elif args.id is not None:
        session = next((s for s in sessions if s.id == args.id), None)
        if session is None:
            print(f"No session found with id {args.id}!")
            exit(1)
    elif len(sessions) == 1:
        session = sessions[0]
    else:
        print("No session specified and no unique session found!")
        exit(1)
    node = beaker.node.get(session.node)
    print(f"Attempting to attach to session {session.name or session.id} on node {node.hostname}...")
    os.execlp("beaker", *f"beaker session attach --remote {session.id}".split())


def launch_interactive(args, extra_args: list[str]):
    beaker = Beaker.from_env()

    try:
        with open(LAUNCH_CONF_PATH, "r") as f:
            conf: dict[str, dict[str, str]] = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"No launch configuration found at {LAUNCH_CONF_PATH}! Create one to use this command.")
        exit(1)

    if args.launch_config not in conf:
        print(f"No launch configuration found for {args.launch_config}!")
        exit(1)

    launch_conf = conf.get(DEFAULT_LAUNCH_CONFIG, {})
    launch_conf.update(conf[args.launch_config])

    clusters = find_clusters(beaker, launch_conf["cluster"])
    if len(clusters) == 0:
        print(f"No clusters found for pattern {launch_conf['cluster']}!")
        exit(1)

    beaker_cmd = f"beaker session create -w {launch_conf['workspace']} --budget {launch_conf['budget']} --remote --bare"
    for cluster in clusters:
        beaker_cmd += f" --cluster {cluster.name}"
    for mount in launch_conf.get("mounts", []):
        beaker_cmd += f" --mount src={mount['src']},ref={mount['ref']},dst={mount['dst']}"
    for env, secret in launch_conf.get("env_secrets", {}).items():
        beaker_cmd += f" --secret-env {env}={secret}"
    if "gpus" in launch_conf:
        beaker_cmd += f" --gpus {launch_conf['gpus']}"

    if len(extra_args) > 0:
        beaker_cmd += f" {' '.join(extra_args)}"

    if args.dry_run:
        print("Would execute:")
        print(beaker_cmd)
    else:
        print(*beaker_cmd.split())
        os.execlp("beaker", *beaker_cmd.split())


class ConfigDumper(yaml.SafeDumper):
    """
    Custom YAML dumper to insert blank lines between top-level objects.
    See: https://github.com/yaml/pyyaml/issues/127#issuecomment-525800484
    """
    def write_line_break(self, data=None):
        super().write_line_break(data)
        if len(self.indents) == 1:
            super().write_line_break()


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


def stop(args, _):
    beaker = Beaker.from_env()
    jobs = beaker.job.list(author=beaker.account.whoami().name)
    if len(jobs) == 0:
        print(f"No sessions found for author {beaker.account.whoami().name}.")
        exit(1)
    elif args.session_idx is not None:
        if args.session_idx < 0 or args.session_idx >= len(jobs):
            print(f"Invalid session index {args.session_idx}!")
            exit(1)
        inter, noninter = get_sessions_and_nodes(beaker)
        if args.session_idx < len(inter):
            job, _ = inter[args.session_idx]
        else:
            job, _ = noninter[args.session_idx - len(inter)]
    elif args.name is not None:
        job = next((s for s in jobs if s.name == args.name), None)
        if job is None:
            print(f"No session found with name {args.name}!")
            exit(1)
    elif args.id is not None:
        job = next((s for s in jobs if s.id == args.id), None)
        if job is None:
            print(f"No session found with id {args.id}!")
            exit(1)
    elif len(jobs) == 1:
        job = jobs[0]
    else:
        print("No session specified and no unique session found!")
        exit(1)

    assert isinstance(job, Job)  # for type checking
    node = beaker.node.get(job.node)
    is_interactive = job.kind == JobKind.session
    print(f"Attempting to stop {'interactive' if is_interactive else 'noninteractive'} session {job.name or job.id} on node {node.hostname}...")
    if is_interactive:
        os.execlp("beaker", *f"beaker session stop {job.id}".split())
    else:
        os.execlp("beaker", *f"beaker job cancel {job.id}".split())


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
