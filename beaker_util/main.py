from argparse import ArgumentParser
import sys
import os
from typing import List, Tuple
import yaml
import re

import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from beaker import Beaker, JobKind, Job, Node

CONF_DIR = os.path.join(os.environ["HOME"], ".beakerutil")
LAUNCH_CONF_PATH = os.path.abspath(os.path.join(CONF_DIR, "launch.conf"))


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
    def print_sessions(title, s: List[Tuple[Job, Node]]):
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

    if not os.path.isfile(LAUNCH_CONF_PATH):
        print(f"No launch configuration found at {LAUNCH_CONF_PATH}! Create one to use this command.")
        exit(1)

    with open(LAUNCH_CONF_PATH, "r") as f:
        conf = yaml.safe_load(f)

    if args.launch_config not in conf:
        print(f"No launch configuration found for {args.launch_config}!")
        exit(1)

    launch_conf: dict[str, str] = conf["DEFAULT"]
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


def add_argument(conf, parser: ArgumentParser, short, long, **kwargs):
    command = parser.prog.split(" ")[-1]
    arg_name = long[2:]
    if command in conf["defaults"]:
        command_defaults = conf["defaults"][command]
        if arg_name in command_defaults:
            t = kwargs.get("type", str)
            kwargs["default"] = t(command_defaults[arg_name])
    if "default" not in kwargs and "required" not in kwargs:
        kwargs["required"] = True
    parser.add_argument(short, long, **kwargs)


def get_args(argv):
    parser = ArgumentParser(prog="beakerutil", description="Collection of utilities for Beaker", allow_abbrev=False)
    subparsers = parser.add_subparsers(required=True, dest="command")

    launch_parser = subparsers.add_parser("launch", help="Launch interactive session on any available node in a cluster.", allow_abbrev=False)
    launch_parser.add_argument("launch_config", help="The launch configuration to use.")
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
