# BeakerUtil

This project is a collection of command-line utilities for [Beaker](https://beaker.org).

This project includes the following features (list will be updated as the package grows)
1. `launch` - Intelligently launch a new interactive beaker session. Given a cluster, finds a node with available resources automatically and launches a session on that node, wrapped in a tmux session in order to keep it alive.

## Installation

1. Ensure that Beaker is set up locally by following [these instructions](https://beaker-docs.apps.allenai.org/start/install.html).
2. Clone this project and `cd` to the project root.
3. Install with `pip install .`

## Usage

The main script is `beakerutil`, which is the entrypoint for all utilities, which are specified as subcommands.
Run `beakerutil -h` for more information.

Note that some arguments, after being specified, will be remembered and won't have to be specified again.

### Using `beakerutil launch`

The first time using `beakerutil launch`, you must specifiy the `--workspace` and `--cluster` parameters. These will be remembered for later.
Note that the budget is hardcoded to `ai2/prior`.

If you specify the `--node` parameter, this node will be preferentially used if it has sufficient available resources.

For example, my first launch looks like this:

```bash
beakerlaunch -w ai2/abhayd -c prior-elanding -i beaker://abhayd/abhayd_torch -s hostpath:///net/nfs2.prior/abhayd -d /root/abhayd -a="--bare"
```

Note the use of the `=` symbol with the `-a` flag. After this command, I can simply run `beakerlaunch` to automatically perform the following steps:

1. Connect to any available node with sufficient resources (Optionally specified with `-g` flag for GPUs)
2. Log in to Beaker on the server if necessary
3. Pull the Beaker image `abhayd/abhayd_torch`
4. Launch a tmux session on the server, within which it launches an interactive Beaker session as root (specified by `--bare` flag)
5. Mount my code from NFS onto the `/root/abhayd` folder in the session and set that as the initial working directory

### Using `beakerutil list`

`beakerutil list` is a straightforward command, it takes no arguments and prints the currently running beaker jobs, both interactive and noninteractive. For example, the output may look like this:
```bash
Interactive sessions:
    0: Session 01JBWFVSS0HNZWW5CT8C84F0J1 using 1 GPU(s) on prior-elanding-62.reviz.ai2.in, status=idle
```
In this case, there is only one session, with index 0 and ID `01JBWFVSS0HNZWW5CT8C84F0J1`.

### Using `beakerutil attach`

Since `beakerutil launch` can launch a session on an unspecified node, it might be annoying to manually connect to the session. `beakerutil attach` can automatically connect to the right node and attach to the correct session. For example, say the output of `beakerutil list` looks like this:
```bash
Interactive sessions:
    0: Session 01JBWFVSS0HNZWW5CT8C84F0J1 using 1 GPU(s) on prior-elanding-62.reviz.ai2.in, status=idle
```
Running `beakerutil attach 0` will connect to the session at index 0. Alternatively, you can specify the session ID or name with the `--id` or `--name` flags, respectively. If you only have one session running (as is the case here), you can simply run `beakerutil attach` (with no arguments) to attach to that session.

### Shortcuts

Some shorthand commands are provided for convenience:
 - `beakerlaunch` is a shorthand for `beakerutil launch`. All arguments are forwarded.
