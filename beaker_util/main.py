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
# maps shells to startup files (paths relative to home) in decreasing order of priority
SHELL_CONF_PATHS = {
    "bash": [".bash_aliases", ".bashrc", ".bash_profile"],
    "zsh": [".zsh_aliases", ".zshrc", ".zprofile"],
    "sh": [".shrc", ".shinit", ".profile"],
    "fish": [os.path.join(".config", "fish", "config.fish")],
    "csh": [".cshrc"],
    "tcsh": [".tcshrc", ".cshrc"],
    "ksh": [".kshrc", ".profile"]
}
SHELL_CONF_PATHS = {
    shell: [os.path.expanduser(os.path.join("~", p)) for p in paths] for shell, paths in SHELL_CONF_PATHS.items()
}

ALIAS_SNIPPET = f"""# >>> BeakerUtil initialize >>>
alias beakerlaunch=\"PYTHON_PATH='{sys.executable}' source beaker_util launch\"
# <<< BeakerUtil initialize <<<\n\n"""
ALIAS_SNIPPET = ALIAS_SNIPPET.replace("\\", "\\\\")  # duplicate backslashes for re.sub
ALIAS_PATTERN = r"# >>> BeakerUtil initialize >>>[\s\S]+?# <<< BeakerUtil initialize <<<\n{0,2}"

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

def init_shell(conf, args, _):
    if args.shell not in SHELL_CONF_PATHS:
        print(f"Unsupported shell: {args.shell}", file=sys.stderr)
        sys.exit(1)
    paths = SHELL_CONF_PATHS[args.shell]
    path = next(filter(os.path.isfile, paths), paths[-1])

    print(f"Adding alias to {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_dotfile(path, ALIAS_PATTERN, ALIAS_SNIPPET, add_if_absent=True)
    if args.shell not in conf["shells"]:
        conf["shells"].append(args.shell)
    save_conf(conf)
    print("Shell initialized! Please close and re-open any existing sessions.")
    return []

def requote(s: str):
    return s.replace('"', "\\\"")

def launch_interactive(conf, args, extra_args):
    cluster_util = Beaker.from_env().cluster.utilization(args.cluster)
    node_gpus = {node_util.hostname: node_util.free.gpu_count for node_util in cluster_util.nodes}
    node_hostname = max(node_gpus.keys(), key=lambda n: node_gpus[n])
    if node_gpus[node_hostname] < args.gpus:
        print("No node with enough GPUs available!")
        exit(1)
    img_arg = f"--image {args.image}" if args.image else ""
    beaker_cmd = f"beaker session create {img_arg} --budget ai2/prior --gpus {args.gpus} --workspace {args.workspace} {' '.join(extra_args)}".strip()
    tmux_cmd = f"tmux new-session \"{requote(beaker_cmd)}\""
    ssh_cmd = f"ssh -t {node_hostname} \"{requote(tmux_cmd)} ; bash\""
    return [ssh_cmd]

def reset(conf, args, _):
    if args.command and args.command in conf["defaults"]:
        del conf["defaults"][args.command]
        print(f"Reset default parameters for command: {args.command}")
    elif not args.command:
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

def get_args(conf):
    parser = ArgumentParser(description="Intelligently spin up an interactive beaker session")
    subparsers = parser.add_subparsers(required=True, dest="command")

    init_parser = subparsers.add_parser("init", help="Register a new shell")
    init_parser.add_argument("shell", help="The name of the shell to register")
    init_parser.set_defaults(func=init_shell)

    reset_parser = subparsers.add_parser("reset", help="Reset previously specified default arguments")
    reset_parser.add_argument("command", nargs="?", help="The command for which the default arguments should be reset. If unspecified, reset all commands.")
    reset_parser.set_defaults(func=reset)

    launch_parser = subparsers.add_parser("launch", help="Launch interactive session on any available node in a cluster")
    add_argument(conf, launch_parser, "-c", "--cluster")
    add_argument(conf, launch_parser, "-i", "--image", required=False)
    add_argument(conf, launch_parser, "-w", "--workspace")
    launch_parser.add_argument("-g", "--gpus", type=int, default=1)
    launch_parser.set_defaults(func=launch_interactive)

    args, extra_args = parser.parse_known_args()
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

def main():
    conf = setup_and_load_conf()
    args, extra_args = get_args(conf)
    commands = args.func(conf, args, extra_args)
    if commands:
        print("\n".join(commands))
        exit(99)

if __name__ == "__main__":
    main()
