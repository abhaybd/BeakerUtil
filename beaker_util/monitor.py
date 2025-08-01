import io
import time
import curses
from datetime import datetime
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor

import fabric
from beaker import Beaker, BeakerJob, BeakerNode, BeakerWorkloadStatus, BeakerWorkloadType
import pandas as pd
from tabulate import tabulate

from beaker_util.utils import inject_beaker


@inject_beaker
def usage_generator(beaker: Beaker):
    workloads = beaker.workload.list(author=beaker.user_name, finalized=False, workload_type=BeakerWorkloadType.experiment)

    experiments: list[tuple[BeakerJob, BeakerNode]] = []
    for workload in workloads:
        job = beaker.workload.get_latest_job(workload)
        if job is not None and job.status.status == BeakerWorkloadStatus.running:
            experiments.append((job, beaker.node.get(job.assignment_details.node_id)))
    experiments.sort(key=lambda x: x[1].hostname + x[0].id)

    hostnames = sorted(set(n.hostname for _, n in experiments))
    with closing(fabric.ThreadingGroup(*hostnames, forward_agent=False)) as smi_connections:
        with closing(fabric.ThreadingGroup(*hostnames, forward_agent=False)) as docker_connections:
            with ThreadPoolExecutor(max_workers=2) as executor:
                while True:
                    smi_output_fut = executor.submit(smi_connections.run, "nvidia-smi --query-gpu=uuid,name,memory.used,memory.total,utilization.gpu --format=csv", hide=True)
                    docker_output_fut = executor.submit(docker_connections.run, "docker stats --no-stream --no-trunc --format json", hide=True)
                    smi_output = smi_output_fut.result()
                    docker_output = docker_output_fut.result()
                    assert isinstance(smi_output, fabric.GroupResult)
                    assert isinstance(docker_output, fabric.GroupResult)
                    node_smi_output: dict[str, pd.DataFrame] = {}
                    for conn, output in smi_output.items():
                        conn: fabric.Connection
                        output: fabric.Result
                        assert isinstance(conn.host, str) and isinstance(output.stdout, str)
                        node_smi_output[conn.host] = pd.read_csv(io.StringIO(output.stdout), skipinitialspace=True)
                        node_smi_output[conn.host].set_index("uuid", inplace=True)
                    node_docker_output: dict[str, pd.DataFrame] = {}
                    for conn, output in docker_output.items():
                        conn: fabric.Connection
                        output: fabric.Result
                        assert isinstance(conn.host, str) and isinstance(output.stdout, str)
                        node_docker_output[conn.host] = pd.read_json(io.StringIO(output.stdout), lines=True)
                        node_docker_output[conn.host].set_index("Name", inplace=True)

                    rows = [["Job", "Hostname", "CPU %", "RAM", "GPU(s)", "GPU %", "VRAM", "Network (In/Out)", "Disk (Write/Read)"]]
                    for job, node in experiments:
                        hostname = node.hostname
                        gpus: list[str] = []
                        vram: list[str] = []
                        gpu_util: list[str] = []
                        if job.assignment_details.HasField("resource_assignment"):
                            smi_df = node_smi_output[hostname]
                            for gpu in job.assignment_details.resource_assignment.gpus:
                                row = smi_df.loc[gpu]
                                gpus.append(row["name"])
                                vram.append(f"{row['memory.used [MiB]']} / {row['memory.total [MiB]']}")
                                gpu_util.append(row['utilization.gpu [%]'])

                        docker_df = node_docker_output[hostname]
                        try:
                            docker_row = docker_df.loc[f"execution-{job.id}".lower()]
                        except KeyError:
                            continue
                        cpu_util: str = docker_row["CPUPerc"]
                        ram: str = docker_row["MemUsage"]
                        network_io: str = docker_row["NetIO"]
                        disk_io: str = docker_row["BlockIO"]

                        rows.append([job.id, hostname, cpu_util, ram, "\n".join(gpus), "\n".join(gpu_util), "\n".join(vram), network_io, disk_io])
                    if len(rows) == 1:
                        break
                    timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
                    table = tabulate(rows, headers="firstrow", tablefmt="grid")
                    yield f"{timestamp}\n{table}"


def monitor(args, _):
    if args.once:
        try:
            with closing(usage_generator()) as gen:
                print(next(gen))
        except StopIteration:
            print("No running experiments detected.")
        return

    exited_by_self = False

    def monitor_curses(stdscr: curses.window):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        with closing(usage_generator()) as gen:
            try:
                while True:
                    loop_start = time.perf_counter()
                    usage_data = next(gen)
                    stdscr.clear()
                    max_y, max_x = stdscr.getmaxyx()
                    lines = usage_data.split('\n')
                    for i, line in enumerate(lines):
                        if i < max_y:
                            stdscr.addstr(i, 0, line[:max_x])
                    stdscr.refresh()
                    loop_end = time.perf_counter()

                    sleep_time = args.interval - (loop_end - loop_start)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
            except KeyboardInterrupt:
                pass
            except StopIteration:
                nonlocal exited_by_self
                exited_by_self = True
            finally:
                curses.curs_set(1)

    curses.wrapper(monitor_curses)
    if exited_by_self:
        print("No more running experiments detected, they may have finished.")
