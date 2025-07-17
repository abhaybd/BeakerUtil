import io
import time
import curses
from datetime import datetime
from contextlib import closing

import fabric
from beaker import Beaker, JobKind
import pandas as pd
from tabulate import tabulate


def usage_generator():
    beaker = Beaker.from_env()
    jobs = beaker.job.list(author=beaker.account.whoami().name)
    if len(jobs) == 0:
        print(f"No jobs found for author {beaker.account.whoami().name}.")
        exit(1)

    experiments = [(j, beaker.node.get(j.node)) for j in jobs if j.kind == JobKind.execution]
    experiments.sort(key=lambda x: x[1].hostname + x[0].id)
    hostnames = sorted(set(n.hostname for _, n in experiments))
    with closing(fabric.ThreadingGroup(*hostnames, forward_agent=False)) as connections:
        while True:
            smi_output = connections.run("nvidia-smi --query-gpu=uuid,name,memory.used,memory.total,utilization.gpu --format=csv", hide=True)
            node_smi_output: dict[str, pd.DataFrame] = {}
            for conn, output in smi_output.items():
                conn: fabric.Connection
                output: fabric.Result
                assert isinstance(conn.host, str) and isinstance(output.stdout, str)
                node_smi_output[conn.host] = pd.read_csv(io.StringIO(output.stdout), skipinitialspace=True)
                node_smi_output[conn.host].set_index("uuid", inplace=True)

            rows = [["Job", "Hostname", "GPU(s)", "VRAM", "GPU Utilization"]]
            for job, node in experiments:
                hostname = node.hostname
                gpus: list[str] = []
                memory: list[str] = []
                utilization: list[str] = []
                if job.limits is not None:
                    smi_df = node_smi_output[hostname]
                    for gpu in job.limits.gpus:
                        row = smi_df.loc[gpu]
                        gpus.append(row["name"])
                        memory.append(f"{row['memory.used [MiB]']} / {row['memory.total [MiB]']}")
                        utilization.append(row['utilization.gpu [%]'])
                rows.append([job.id, hostname, "\n".join(gpus), "\n".join(memory), "\n".join(utilization)])
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            table = tabulate(rows, headers="firstrow", tablefmt="grid")
            yield f"{timestamp}\n{table}"


def monitor(args, _):
    if args.once:
        with closing(usage_generator()) as gen:
            print(next(gen))
        return

    def monitor_curses(stdscr):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        max_y, max_x = stdscr.getmaxyx()

        with closing(usage_generator()) as gen:
            try:
                while True:
                    stdscr.clear()
                    usage_data = next(gen)
                    lines = usage_data.split('\n')
                    for i, line in enumerate(lines):
                        if i < max_y:
                            stdscr.addstr(i, 0, line[:max_x])

                    stdscr.refresh()
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
            finally:
                curses.curs_set(1)
    
    curses.wrapper(monitor_curses)


if __name__ == "__main__":
    monitor(None, None)
