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

### Shortcuts

Some shorthand commands are provided for convenience:
 - `beakerlaunch` is a shorthand for `beakerutil launch`. All arguments are forwarded.
