from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys

from .workflow import STAGES, Workflow, read_json, resolve_stage


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def run_stage(workflow, stage, runner, timeout):
    packet = workflow.prepare(stage)
    if not runner:
        emit(packet)
        return False
    # An explicitly supplied local program owns model credentials and read-only tools.
    # Never interpret runner arguments through a shell.
    response = subprocess.run(shlex.split(runner), input=json.dumps(packet, ensure_ascii=False),
                              text=True, capture_output=True, timeout=timeout, check=True)
    workflow.save(stage, json.loads(response.stdout))
    emit({"stage": stage, "status": "complete"})
    return True


def execute(workflow, words, runner=None, timeout=300):
    if not words:
        raise ValueError("请输入 /research 等阶段命令，或 /plans")
    command = words[0].lstrip("/")
    if command == "plans":
        if len(words) == 2 and words[1] == "status":
            emit(workflow.snapshot()[0])
        elif len(words) == 2 and words[1] == "overview":
            print(workflow.render_reports())
        elif len(words) == 1:
            for stage in STAGES:
                if workflow.snapshot()[0][stage]["status"] == "complete":
                    continue
                if not run_stage(workflow, stage, runner, timeout):
                    print("当前为宿主执行模式：完成本任务包后用 accept 导入，再继续 /plans。", file=sys.stderr)
                    break
            else:
                print(workflow.render_reports())
        else:
            raise ValueError("用法：/plans [status|overview]")
    elif command == "accept" and len(words) == 3:
        print(workflow.save(resolve_stage(words[1]), read_json(words[2])))
    elif command == "prepare" and len(words) == 2:
        emit(workflow.prepare(resolve_stage(words[1])))
    elif len(words) == 1:
        run_stage(workflow, resolve_stage(command), runner, timeout)
    else:
        raise ValueError("产品由 --project 指定；用法：/<阶段> 或 accept <阶段> <结果.json>")


def main(argv=None):
    parser = argparse.ArgumentParser(description="PLANTS 通用 PLANS 价值工程编排器")
    parser.add_argument("--project", required=True, help="项目 JSON 配置")
    parser.add_argument("--data-dir", help="独立运行数据根目录，默认 plants/data")
    parser.add_argument("--runner", help="外部程序：stdin 接收任务包，stdout 返回结果 JSON")
    parser.add_argument("--timeout", type=float, default=300, help="外部运行器超时秒数")
    parser.add_argument("command", nargs="*")
    args = parser.parse_args(argv)
    try:
        workflow = Workflow(args.project, args.data_dir)
        if args.timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        if args.command:
            execute(workflow, args.command, args.runner, args.timeout)
        else:
            print("PLANTS · 12 阶段 /research … /costsystem；/plans；/plans status；/exit")
            while True:
                try:
                    line = input("PLANTS> ").strip()
                    if line in ("/exit", "exit", "quit"):
                        break
                    if line:
                        execute(workflow, shlex.split(line), args.runner, args.timeout)
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    print(f"错误：{exc}", file=sys.stderr)
                except EOFError:
                    break
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

