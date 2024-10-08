from argparse import ArgumentParser
import sys
import os
import yaml
import re

import fabric

import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from beaker import Beaker

CONF_PATH = os.path.join(os.environ["HOME"], ".beakerutil.conf")


def setup_and_load_conf():
    # perform first time setup, if necessary
    init_conf = {
        "defaults": {},
        "shells": []
    }
    if not os.path.isfile(CONF_PATH):
        conf = init_conf
        save_conf(conf)
    else:
        conf = load_conf()
        changed = False
        for k, v in init_conf.items():
            if k not in conf:
                conf[k] = v
                changed = True
        if changed:
            save_conf(conf)
    return conf


def load_conf():
    with open(CONF_PATH) as f:
        conf = yaml.safe_load(f)
    return conf


def save_conf(conf):
    with open(CONF_PATH, "w") as f:
        yaml.dump(conf, f)


def write_dotfile(path, pattern, repl, add_if_absent=True):
    if os.path.isfile(path):
        with open(path) as f:
            contents = f.read()
    else:
        contents = ""
    if re.search(pattern, contents):
        contents = re.sub(pattern, repl, contents)
    elif add_if_absent:
        contents += repl
    with open(path, "w") as f:
        f.write(contents)


def requote(s: str):
    return s.replace("\\", "\\\\").replace('"', "\\\"")


def launch_interactive(_, args, extra_args: list):
    beaker = Beaker.from_env()
    cluster_util = beaker.cluster.utilization(args.cluster)
    node_gpus = {node_util.hostname: node_util.free.gpu_count for node_util in cluster_util.nodes}
    node_hostname = max(node_gpus.keys(), key=lambda n: node_gpus[n])
    if node_gpus[node_hostname] < args.gpus:
        print("No node with enough GPUs available!")
        exit(1)
    if args.node:
        if not args.node.endswith(".reviz.ai2.in"):
            args.node += ".reviz.ai2.in"
        if args.node not in node_gpus:
            print(f"Node {args.node} not found in the cluster, using node {node_hostname} instead.")
        elif node_gpus[args.node] < args.gpus:
            print(f"Node {args.node} has insufficient GPUs, using node {node_hostname} instead.")
        else:
            node_hostname = args.node

    print(f"Launching interactive session on node {node_hostname} with {args.gpus} GPUs")
    print("Logging into beaker...")
    conn = fabric.Connection(node_hostname)
    conn.run(f"beaker config set user_token {beaker.account.config.user_token}")

    if args.image:
        if not args.image.startswith("beaker://"):
            args.image = f"beaker://{args.image}"
        img_name = args.image[len("beaker://"):]
        print(f"Pulling beaker image {img_name}...")
        conn.run(f"beaker image pull {img_name}")
    conn.close()

    img_arg = f"--image {args.image}" if args.image else ""
    if args.mount_src and args.mount_dst:
        extra_args.append(f"--mount {args.mount_src}={args.mount_dst}")
        extra_args.append(f"--workdir {args.mount_dst}")
    beaker_cmd = (f"beaker session create {img_arg}"
                  + f" --budget ai2/prior --gpus {args.gpus} --workspace {args.workspace}"
                  + f" {args.additional_args or ''} {' '.join(extra_args)}").strip()
    tmux_cmd = f"tmux new-session \"{requote(beaker_cmd)}\""
    os.execlp("ssh", "ssh", "-t", node_hostname, f"{tmux_cmd} ; bash")


def reset(conf, args, _):
    if args.reset_cmd:
        if args.reset_cmd not in conf["defaults"]:
            print(f"No default parameters set for command: {args.reset_cmd}")
        elif args.arg:
            if args.arg not in conf["defaults"][args.reset_cmd]:
                print(f"No default parameter set for argument: {args.arg}")
            else:
                del conf["defaults"][args.reset_cmd][args.arg]
                print(f"Reset default parameter for argument: {args.arg}")
        else:
            del conf["defaults"][args.reset_cmd]
            print(f"Reset default parameters for command: {args.reset_cmd}")
    else:
        conf["defaults"] = {}
        print("Reset default parameters for all commands.")
    save_conf(conf)


def add_argument(conf, parser: ArgumentParser, short, long, **kwargs):
    command = parser.prog.split(" ")[-1]
    if command in conf["defaults"]:
        command_defaults = conf["defaults"][command]
        if long[2:] in command_defaults:
            kwargs["default"] = command_defaults[long[2:]]
    if "default" not in kwargs and "required" not in kwargs:
        kwargs["required"] = True
    parser.add_argument(short, long, **kwargs)


def get_args(conf, argv):
    parser = ArgumentParser(prog="beakerutil", description="Collection of utilities for Beaker")
    subparsers = parser.add_subparsers(required=True, dest="command")

    reset_parser = subparsers.add_parser("reset", help="Reset previously specified arguments")
    reset_parser.add_argument("reset_cmd", nargs="?", metavar="command",
                              help="The command for which the default arguments should be reset. If unspecified, reset all commands.")
    reset_parser.add_argument("arg", nargs="?", help="The argument to reset. If unspecified, reset all arguments for the command.")
    reset_parser.set_defaults(func=reset)

    launch_parser = subparsers.add_parser(
        "launch", help="Launch interactive session on any available node in a cluster. All arguments except -g are remembered.")
    add_argument(conf, launch_parser, "-c", "--cluster", help="The cluster to launch the session on")
    add_argument(conf, launch_parser, "-w", "--workspace", help="The workspace to launch the session in")
    add_argument(conf, launch_parser, "-n", "--node", required=False, help="Preferred node to launch the session on")
    add_argument(conf, launch_parser, "-i", "--image", required=False, help="The beaker image to use for the session")
    add_argument(conf, launch_parser, "-s", "--mount_src", required=False, help="Network location to mount to the container")
    add_argument(conf, launch_parser, "-d", "--mount_dst", required=False, help="Mount destination in the container")
    add_argument(conf, launch_parser, "-a", "--additional_args", required=False, help="Additional arguments to pass verbatim to beaker")
    launch_parser.add_argument("-g", "--gpus", type=int, default=1)
    launch_parser.set_defaults(func=launch_interactive)

    args, extra_args = parser.parse_known_args(argv)
    assert len(extra_args) == 0 or extra_args[0] == "--", f"Unknown extra arguments: {extra_args}"
    extra_args = extra_args[1:]

    if args.command not in conf["defaults"]:
        conf["defaults"][args.command] = {}
    for attr in dir(args):
        if attr[0] != "_":
            v = getattr(args, attr)
            if isinstance(v, str):
                conf["defaults"][args.command][attr] = v
    save_conf(conf)
    return args, extra_args


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    conf = setup_and_load_conf()
    args, extra_args = get_args(conf, argv)
    args.func(conf, args, extra_args)


if __name__ == "__main__":
    main()
