# BeakerUtil

This project is a collection of command-line utilities for [Beaker](https://beaker.org).

## Installation

1. Ensure that Beaker is set up locally by following [these instructions](https://beaker-docs.apps.allenai.org/start/install.html).
2. Install this project with `pip install git+https://github.com/abhaybd/BeakerUtil.git`

## Usage

The main script is `beakerutil`, which is the entrypoint for all utilities, which are specified as subcommands.
Run `beakerutil -h` for more information.

### Using `beakerutil launch`

With BeakerUtil, you can specify different launch configurations in `~/.beakerutil/launch.conf`, with different parameters. Clusters can be specified with a regex to match to multiple clusters. Additionally, the `DEFAULT` configuration specify parameters to be applied for every launch configuration, but can be overridden. For example, this is my `launch.conf`:

```
DEFAULT:
    budget: ai2/prior
    workspace: ai2/abhayd
    env_secrets:
        AWS_SECRET_ACCESS_KEY: AWS_ACCESS_KEY
        AWS_ACCESS_KEY_ID: AWS_ACCESS_KEY_ID
        WANDB_API_KEY: WANDB_API_KEY
        HF_TOKEN: HF_TOKEN
        GEMINI_API_KEY: GEMINI_API_KEY
        OPENAI_API_KEY: OPENAI_API_KEY
        DOCKER_PAT: DOCKER_PAT

phobos:
    cluster: ai2/phobos-cirrascale
    mounts:
        - src: weka
          ref: prior-default
          dst: /weka/prior
        - src: weka
          ref: oe-training-default
          dst: /weka/oe-training-default

gpu:
    cluster: ".*-cirrascale.*"
    gpus: 1
    mounts:
        - src: weka
          ref: prior-default
          dst: /weka/prior
        - src: weka
          ref: oe-training-default
          dst: /weka/oe-training-default

elanding:
    cluster: "ai2/prior-elanding.*"
```

#### Extra Arguments

Extra arguments to pass to `beaker session create` can also be passed as additional positional arguments preceded by the delimeter `--`. For example, to name the interactive session, you could do:

```bash
beakerlaunch -- -n foo
```

### Using `beakerutil list`

`beakerutil list` is a straightforward command, it takes no arguments and prints the currently running beaker jobs, both interactive and noninteractive. For example, the output may look like this:
```bash
Interactive sessions:
    0: Session 01JBWFVSS0HNZWW5CT8C84F0J1 using 1 GPU(s) on prior-elanding-62.reviz.ai2.in, status=idle
```
In this case, there is only one session, with index 0 and ID `01JBWFVSS0HNZWW5CT8C84F0J1`.

### Using `beakerutil attach`

`beakerutil attach` is a utility for connecting to an existing session with `beaker session attach`. For example, say the output of `beakerutil list` looks like this:
```bash
Interactive sessions:
    0: Session 01JBWFVSS0HNZWW5CT8C84F0J1 using 1 GPU(s) on prior-elanding-62.reviz.ai2.in, status=idle
```
Running `beakerutil attach 0` will connect to the session at index 0. Alternatively, you can specify the session ID or name with the `--id` or `--name` flags, respectively. If you only have one session running (as is the case here), you can simply run `beakerutil attach` (with no arguments) to attach to that session.

### Shortcuts

Some shorthand commands are provided for convenience:
 - `beakerlaunch` is a shorthand for `beakerutil launch`. All arguments are forwarded.
