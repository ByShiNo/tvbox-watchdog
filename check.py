#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B 仓（tvbox-watchdog）互监控判活脚本。

职责：定时读 A 仓（tvbox-selfheal）的 Actions API 最近一次 run 时间；
若超过阈值判定停摆，则 enable + dispatch 把 A 仓 workflow 拉起来。

仅用标准库。token 缺失时仍能检测+记录（匿名读公开仓），但自恢复需 GH_TOKEN。
"""
import datetime
import json
import os
import urllib.request

TARGET_REPO = os.environ.get("TARGET_REPO", "ByShiNo/tvbox-selfheal")
TARGET_WORKFLOW = os.environ.get("TARGET_WORKFLOW", "heal.yml")
MAX_AGE_HOURS = float(os.environ.get("MAX_AGE_HOURS", "8"))
TOKEN = os.environ.get("GH_TOKEN", "")


def api(method, path, body=None):
    url = "https://api.github.com/repos/%s/%s" % (TARGET_REPO, path)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tvbox-watchdog/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
        return r.status, (json.loads(raw) if raw.strip() else None)


def age_hours(created_at):
    dt = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    )
    return (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600.0


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = {
        "check_time": now,
        "target": TARGET_REPO,
        "target_workflow": TARGET_WORKFLOW,
        "max_age_hours": MAX_AGE_HOURS,
        "has_token": bool(TOKEN),
    }
    try:
        st, data = api("GET", "actions/workflows/%s/runs?per_page=1" % TARGET_WORKFLOW)
        runs = data.get("workflow_runs", [])
        if not runs:
            raise RuntimeError("目标 workflow 无运行记录")
        last = runs[0]
        created = last["created_at"]
        age = age_hours(created)
        state.update({
            "last_run": created,
            "age_hours": round(age, 2),
            "conclusion": last.get("conclusion"),
            "status": last.get("status"),
        })
        print("[watchdog] 目标最近run=%s 年龄=%.1fh 结论=%s" % (
            created, age, last.get("conclusion")))

        if age > MAX_AGE_HOURS:
            print("[watchdog] !! 停摆：目标仓 %s 已 %.1fh 未运行，执行自恢复" % (
                TARGET_REPO, age))
            state["health"] = "STALE_RECOVERING"
            if TOKEN:
                try:
                    api("PUT", "actions/workflows/%s/enable" % TARGET_WORKFLOW)
                    print("[watchdog] 已 enable 目标 workflow")
                    state["enabled"] = True
                except Exception as e:
                    print("[watchdog] enable 失败：%s" % e)
                    state["enabled"] = False
                try:
                    api("POST", "actions/workflows/%s/dispatches" % TARGET_WORKFLOW,
                        {"ref": "main"})
                    print("[watchdog] 已 dispatch 目标 workflow")
                    state["dispatched"] = True
                except Exception as e:
                    print("[watchdog] dispatch 失败：%s" % e)
                    state["dispatched"] = False
            else:
                print("[watchdog] 无 GH_TOKEN，仅记录停摆，无法自恢复")
                state["health"] = "STALE_NO_TOKEN"
        else:
            print("[watchdog] 心跳正常")
            state["health"] = "HEALTHY"
    except Exception as e:
        print("[watchdog] 检测失败：%s" % e)
        state["health"] = "CHECK_ERROR"
        state["error"] = str(e)

    with open("state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    main()
