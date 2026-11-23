# TVBox 互监控 Watchdog（B 方案）

## 它解决什么

A 仓（`ByShiNo/tvbox-selfheal`）的自愈 workflow 每 3 小时探测并切源，但它**不能监控自己**——万一被平台禁用或连续失败，没人把它拉起来。

本仓（B）就是 A 的外部看门狗：**每 3 小时读 A 仓的 Actions API 心跳，发现 A 停摆就自动 `enable` + `dispatch` 把它拉起来**。全程在 GitHub 内完成，零外部依赖、零成本。

## 架构

```
B仓 watchdog.yml 每3h第15分触发（错峰）
  → check.py 读 A仓 heal.yml 最近一次 run 时间
  → 年龄 > 8h？
       ├─ 否：写 state.json(H healthy) → commit 保活
       └─ 是：enable A的heal.yml + dispatch 补跑 → 写 state.json(STALE_RECOVERING) → commit
```

A、B 各自每轮都 commit（state.json 时间戳每次不同），两个仓都永远活跃，都不触发 60 天闲置禁用规则。

## 部署状态

- 仓：`https://github.com/ByShiNo/tvbox-watchdog`（Public）
- workflow：`watchdog.yml`，每 3h 第 15 分 UTC 触发
- 监控目标：`ByShiNo/tvbox-selfheal` 的 `heal.yml`

## 需要的 Secret（可选但推荐）

B 仓 → Settings → Secrets and variables → Actions → New repository secret：
- Name: `GH_TOKEN`
- Value: 一个有 `repo` 或 `actions:write` 权限的 GitHub PAT

**不填也能跑**：check.py 匿名读公开仓 Actions API 做检测 + commit 保活；但 A 真停摆时无法 enable/dispatch（会记录到 state.json 的 `health=STALE_NO_TOKEN`）。填了才能自恢复。

## 验证

- 手动触发：Actions → TVBox 互监控 Watchdog → Run workflow
- 看 `state.json`：`health` 应为 `HEALTHY`，`age_hours` 为 A 仓最近 run 距今小时数
- 故障注入：把 `MAX_AGE_HOURS` 临时改为 `0.01`，触发一次，看是否执行 enable+dispatch（然后改回 8）

## 与 A 方案 / SCF 方案的关系

| 方案 | 部署位置 | 成本 | 告警 |
|---|---|---|---|
| A（纯保活） | A 仓自身 commit | 0 | 无 |
| B（本仓） | GitHub 第二个仓 | 0 | 仓库内 state.json |
| SCF | 腾讯云函数 | 免费额度内 | Bark/微信推送 |

三个可共存，互不冲突。家用场景 A+B 已经够；要手机告警再上 SCF。
