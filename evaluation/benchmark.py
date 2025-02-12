#!/usr/bin/env python3

import argparse
import csv
import functools
import re
import subprocess
import sys
from pathlib import Path
import time
import io
import statistics
import math
import json

def get_trials(out_path, from_dir, to_dir):
    out_dir = Path(out_path)
    if not out_dir.is_dir():
        raise Exception(f"output directory {out_dir} does not exist")

    start = None if from_dir is None else int(from_dir)
    end = None if to_dir is None else int(to_dir)
    trials = []
    for path in out_dir.glob("*"):
        if path.is_dir():
            path_time = int(path.stem)

            within_start = True if start is None else start <= path_time
            within_end = True if end is None else path_time <= end
            if within_start and within_end:
                trials.append(path)

    return trials


def bench_compile(args):
    print("benchmarking compilation time")

    cfg_path = Path(args.cfg_file)
    with open(cfg_path) as cfg_file:
      compile_benchmarks = json.loads(cfg_file.read())

    in_dir = Path(args.in_path)

    timestamps = []
    benchmarks = sorted(compile_benchmarks.keys())
    for trial in range(args.trials):
        timestamp = str(int(time.time()))
        timestamps.append(timestamp)

        out_dir = Path(args.out_path, timestamp)
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"starting trial {trial+1}")
        print(f"storing trial data in {out_dir}")

        for bench in benchmarks:
            for cfg in compile_benchmarks[bench]:
                cfg_name = cfg["name"]
                benchfile = Path(args.in_path, f"{bench}.tlhe")
                backend = cfg["backend"]
                size = cfg["size"]
                opt_duration = cfg["opt_duration"]
                node_limit = cfg.get("node_limit", 500)
                epochs = cfg["epochs"]
                
                print(f"compiling {cfg_name}-{bench}")

                cmd = f"./he_vectorizer -b {backend} -s {size} -e {epochs} -d {opt_duration} -n {node_limit} {benchfile}"

                compile_proc = subprocess.run(
                    cmd.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True,
                    encoding="utf-8",
                    env={"RUST_LOG": "he_vectorizer=info"}
                )

                out_filename = Path(out_dir, f"{cfg_name}-{bench}.txt")
                out_filename.touch(exist_ok=False)
                with open(out_filename, "w") as out_file:
                    out_file.write(compile_proc.stdout)

        print(f"finished trial {trial+1}")

    with open(args.exp_file, "w") as exp_file:
        out_dirs = [str(Path(args.out_path, timestamp)) for timestamp in timestamps]
        exp_data = {
            "benchmarks": compile_benchmarks,
            "trials": out_dirs
        }
        exp_file.write(json.dumps(exp_data, indent=4))

    print(f"saved experiment metadata at {args.exp_file}")


def collect_compile(args):
    with open(args.exp_file) as exp_file:
        exp_data = json.loads(exp_file.read())

    compile_benchmarks = exp_data["benchmarks"]
    trials = exp_data["trials"]
    n = len(trials)
    if n == 0:
        print("no trials found in that time interval")
        return

    elif n == 1:
        print("cannot compute standard error with only one trial")
        return

    csv_out = io.StringIO()
    fields = [
        "bench","cfg","trials",
        "scheduling","scheduling_sterror","scheduling_error_pct",
        "optimization","optimization_sterror","optimization_error_pct",
        "total","total_sterror","total_error_pct",
    ]
    writer = csv.DictWriter(csv_out, fieldnames=fields)
    writer.writeheader()
    benchmarks = sorted(compile_benchmarks.keys())
    for bench in benchmarks:
        for cfg in compile_benchmarks[bench]:
            cfg_name = cfg["name"]
            scheduling_times = []
            optimization_times = []
            total_times = []
            for trial in trials:
                cfg_bench = Path(trial, f"{cfg_name}-{bench}.txt")
                if not cfg_bench.is_file():
                    raise Exception(f"expected output file {cfg_bench} does not exist")

                with open(cfg_bench) as cfg_bench_file:
                    cfg_bench_out = cfg_bench_file.read()
                    scheduling_res = re.search("scheduling: (?P<scheduling>[0-9]+)ms", cfg_bench_out)
                    optimization_res = re.search("circuit optimization: (?P<optimization>[0-9]+)ms", cfg_bench_out)
                    total_res = re.search("total compile time: (?P<total>[0-9]+)ms", cfg_bench_out)

                    scheduling_times.append(int(scheduling_res.group("scheduling")))
                    optimization_times.append(int(optimization_res.group("optimization")))
                    total_times.append(int(total_res.group("total")))

            assert(len(scheduling_times) == n)
            assert(len(optimization_times) == n)
            assert(len(total_times) == n)

            scheduling_mean = round(statistics.mean(scheduling_times), 2)
            scheduling_sterror = round(statistics.stdev(scheduling_times) / math.sqrt(n), 2)
            scheduling_error_pct = round(scheduling_sterror / scheduling_mean, 2)

            optimization_mean = round(statistics.mean(optimization_times), 2)
            if optimization_mean > 0:
                optimization_sterror = round(statistics.stdev(optimization_times) / math.sqrt(n), 2)
                optimization_error_pct = round(optimization_sterror / optimization_mean, 2)
            else:
                optimization_sterror = 0
                optimization_error_pct = 0

            total_mean = round(statistics.mean(total_times), 2)
            total_sterror = round(statistics.stdev(total_times) / math.sqrt(n), 2)
            total_error_pct = round(total_sterror / total_mean, 2)

            writer.writerow({
                "bench": bench,
                "cfg": cfg_name,
                "trials": n,
                "scheduling": scheduling_mean,
                "scheduling_sterror": scheduling_sterror,
                "scheduling_error_pct": scheduling_error_pct,
                "optimization": optimization_mean,
                "optimization_sterror": optimization_sterror,
                "optimization_error_pct": optimization_error_pct,
                "total": total_mean,
                "total_sterror": total_sterror,
                "total_error_pct": total_error_pct,
            })

    print(csv_out.getvalue())


def diff_compile(args):
    with open(args.exp_file) as exp_file:
        exp_data = json.loads(exp_file.read())

    compile_benchmarks = exp_data["benchmarks"]
    trials = exp_data["trials"]
    n = len(trials)
    if n < 2:
        print("need at least two trials to diff")
        return

    csv_out = io.StringIO()
    fields = [
        "bench","cfg","trials",
        "scheduling","scheduling_sterror","scheduling_error_pct",
        "optimization","optimization_sterror","optimization_error_pct",
        "total","total_sterror","total_error_pct",
    ]
    writer = csv.DictWriter(csv_out, fieldnames=fields)
    writer.writeheader()
    benchmarks = sorted(compile_benchmarks.keys())
    for bench in benchmarks:
        for cfg in compile_benchmarks[bench]:
            cfg_name = cfg["name"]
            scheduling_times = []
            optimization_times = []
            total_times = []

            first = None
            rest = []
            for trial in trials:
                cfg_bench = Path(trial, f"{cfg_name}-{bench}.txt")
                if not cfg_bench.is_file():
                    raise Exception(f"expected output file {cfg_bench} does not exist")

                if first is None:
                    first = cfg_bench

                else:
                    rest.append(cfg_bench)

            for trial in rest:
                cmd = f"diff {first} {trial}"
                diff_proc = subprocess.run(
                    cmd.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8"
                )

                print(cmd)
                print(diff_proc.stdout)
            

def bench_exec(args):
    print("benchmarking execution time")

    cfg_path = Path(args.cfg_file)
    with open(cfg_path) as cfg_file:
      exec_benchmarks = json.loads(cfg_file.read())

    in_dir = Path(args.in_path)

    timestamps = []
    benchmarks = sorted(exec_benchmarks.keys())
    for trial in range(args.trials):
        timestamp = str(int(time.time()))
        timestamps.append(timestamp)

        out_dir = Path(args.out_path, timestamp)
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"starting trial {trial+1} at {out_dir}")

        for bench in benchmarks:
            bench_input = Path(in_dir, f"input-{bench}.json")

            if not bench_input.is_file():
                raise Exception(f"input file {bench_input} does not exist")

            with open(bench_input) as input_file:
                input_str = input_file.read()

                for cfg in exec_benchmarks[bench]:
                    cfg_bench = f"{cfg}-{bench}"
                    cfg_bench_file = Path(in_dir, f"{cfg_bench}.py")
                    if not bench_input.is_file():
                        raise Exception(f"benchmark file {bench_input} does not exist")

                    print(f"running {cfg_bench}...")

                    bench_proc = subprocess.run(
                        ["python3", cfg_bench_file],
                        input=input_str,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=True,
                        encoding="utf-8"
                    )

                    out_filename = Path(out_dir, f"{cfg_bench}.txt")
                    out_filename.touch(exist_ok=False)
                    with open(out_filename, "w") as out_file:
                        out_file.write(bench_proc.stdout)

                        print(f"dumped output to {out_filename}")
                        time.sleep(1)

        print(f"finished trial {trial+1}")

    with open(args.exp_file, "w") as exp_file:
        out_dirs = [str(Path(args.out_path, timestamp)) for timestamp in timestamps]
        exp_data = {
            "benchmarks": exec_benchmarks,
            "trials": out_dirs
        }
        exp_file.write(json.dumps(exp_data, indent=4))

    print(f"saved experiment metadata at {args.exp_file}")

def collect_exec(args):
    with open(args.exp_file) as exp_file:
        exp_data = json.loads(exp_file.read())

    exec_benchmarks = exp_data["benchmarks"]
    trials = exp_data["trials"]
    n = len(trials)
    if n == 0:
        print("no trials found in that time interval")
        return

    elif n == 1:
        print("cannot compute standard error with only one trial")
        return

    csv_out = io.StringIO()
    fields = ["bench","cfg","trials","exec_time","sterror","error_pct"]
    writer = csv.DictWriter(csv_out, fieldnames=fields)
    writer.writeheader()
    benchmarks = sorted(exec_benchmarks.keys())
    for bench in benchmarks:
        for cfg in exec_benchmarks[bench]:
            exec_times = []
            for trial in trials:
                cfg_bench = Path(trial, f"{cfg}-{bench}.txt")
                if not cfg_bench.is_file():
                    raise Exception(f"expected output file {cfg_bench} does not exist")

                with open(cfg_bench) as cfg_bench_file:
                    cfg_bench_out = cfg_bench_file.read()
                    res = re.search("exec duration: (?P<time>[0-9]+)ms", cfg_bench_out)
                    exec_time = int(res.group("time"))
                    exec_times.append(exec_time)

            assert(len(exec_times) == n)
            mean = statistics.mean(exec_times)
            stdev = statistics.stdev(exec_times)
            sterror = stdev / math.sqrt(n)
            writer.writerow({
                "bench": bench,
                "cfg": cfg,
                "trials": n,
                "exec_time": round(mean, 2),
                "sterror": round(sterror, 2),
                "error_pct": round(sterror / mean, 2)
            })

    print(csv_out.getvalue())


def argument_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="COMMAND", required=True)

    # benchmark compile data
    bench_compile_parser = subparsers.add_parser("bench-compile", help="benchmark compilation time")
    bench_compile_parser.set_defaults(func=bench_compile)

    bench_compile_parser.add_argument(
        "-c", "--config", dest="cfg_file", type=str, required=True,
        help="configuration of benchmarks to execute")

    bench_compile_parser.add_argument(
        "-e", "--experiment", dest="exp_file", type=str, required=True,
        help="name of file to dump experiment metadata")

    bench_compile_parser.add_argument(
        "-t", "--trials", dest="trials", type=int, default=1,
        help="number of times to compile each benchmark")

    bench_compile_parser.add_argument(
        "-i", "--inpath", dest="in_path", type=str, default="",
        help="base path to retrieve benchmarks")

    bench_compile_parser.add_argument(
        "-o", "--outpath", dest="out_path", type=str, default="bench-compile",
        help="base path to store trial information")

    # collect compilation data
    collect_compile_parser = subparsers.add_parser("collect-compile", help="collect compilation data")
    collect_compile_parser.set_defaults(func=collect_compile)

    collect_compile_parser.add_argument(
        "-e" "--exp", dest="exp_file", type=str,
        help="name of experiment file")

    # diff compilation data between trials
    diff_compile_parser = subparsers.add_parser("diff-compile", help="diff compilation data")
    diff_compile_parser.set_defaults(func=diff_compile)

    diff_compile_parser.add_argument(
        "-e" "--exp", dest="exp_file", type=str,
        help="name of experiment file")

    # benchmark execution data
    bench_exec_parser = subparsers.add_parser("bench-exec", help="benchmark execution time")
    bench_exec_parser.set_defaults(func=bench_exec)

    bench_exec_parser.add_argument(
        "-c", "--config", dest="cfg_file", type=str, required=True,
        help="configuration of benchmarks to execute")

    bench_exec_parser.add_argument(
        "-e", "--experiment", dest="exp_file", type=str, required=True,
        help="name of file to dump experiment metadata")

    bench_exec_parser.add_argument(
        "-t", "--trials", dest="trials", type=int, default=1,
        help="number of times to run each benchmark")

    bench_exec_parser.add_argument(
        "-o", "--outpath", dest="out_path", type=str, default="bench-exec",
        help="base path to store trial information")

    bench_exec_parser.add_argument(
        "-i", "--inpath", dest="in_path", type=str, default="",
        help="base path to retrieve benchmarks")

    # collect execution data
    collect_exec_parser = subparsers.add_parser("collect-exec", help="collect execution data")
    collect_exec_parser.set_defaults(func=collect_exec)

    collect_exec_parser.add_argument(
        "-e" "--exp", dest="exp_file", type=str,
        help="name of experiment file")

    return parser


if __name__ == "__main__":
    arguments = argument_parser().parse_args()
    arguments.func(arguments)

