from argparse import ArgumentParser
import sys
import os
import yaml
import re

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
    cluster_util = Beaker.from_env().cluster.utilization(args.cluster)
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
    img_arg = f"--image {args.image}" if args.image else ""
    if args.mount_src and args.mount_dst:
        extra_args.append(f"--mount {args.mount_src}={args.mount_dst}")
        extra_args.append(f"--workdir {args.mount_dst}")
    beaker_cmd = f"beaker session create {img_arg} --budget ai2/prior --gpus {args.gpus} --workspace {args.workspace} {args.additional_args or ''} {' '.join(extra_args)}".strip()
    tmux_cmd = f"tmux new-session \"{requote(beaker_cmd)}\""
    os.execlp("ssh", "ssh", "-t", node_hostname, f"{tmux_cmd} ; bash")


def reset(conf, args, _):
    if args.reset_cmd and args.reset_cmd in conf["defaults"]:
        del conf["defaults"][args.reset_cmd]
        print(f"Reset default parameters for command: {args.reset_cmd}")
    elif not args.reset_cmd:
        conf["defaults"] = {}
        print("Reset default parameters for all commands.")
    save_conf(conf)


def add_argument(conf, parser, short, long, **kwargs):
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
    reset_parser.set_defaults(func=reset)

    launch_parser = subparsers.add_parser("launch", help="Launch interactive session on any available node in a cluster")
    add_argument(conf, launch_parser, "-c", "--cluster")
    add_argument(conf, launch_parser, "-w", "--workspace")
    add_argument(conf, launch_parser, "-n", "--node", required=False, help="Preferred node to launch the session on")
    add_argument(conf, launch_parser, "-i", "--image", required=False)
    add_argument(conf, launch_parser, "-s", "--mount_src", required=False, help="Network location to mount to the container")
    add_argument(conf, launch_parser, "-d", "--mount_dst", required=False, help="Mount destination in the container")
    add_argument(conf, launch_parser, "-a", "--additional_args", required=False,
                 help="Additional arguments to pass to beaker, that will be remembered for future launches")
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
