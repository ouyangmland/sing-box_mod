# sing-box_mod 修复维护清单（禁止破坏性更改）

本文档用于维护 `sing-box_mod` 的本地修复项。
同步上游、重构或清理差异时，必须先核对本文件。

## 1. 不可破坏原则

- 禁止在无等价替代与回归验证的情况下删除已登记修复。
- 禁止以“清理差异”为由移除性能/稳定性修复。
- 禁止未更新本文件就引入、修改或删除本地补丁。
- 若上游已等价修复，可移除本地补丁，但必须在本文件记录“替代来源、版本、验证结果”。

## 2. 已登记修复

### FIX-ROUTE-MONITOR-001

- 状态：启用（必须保留）
- 目标：避免在 Linux 默认接口检测中因路由表规模过大导致 CPU/内存显著占用。
- 实现：
  - 通过 socket 选路推断默认出口接口，避免全量路由表扫描。
  - 在 `route/network.go` 使用 `newDefaultInterfaceMonitor(...)`。
- 文件：
  - `route/default_interface_monitor_linux.go`
  - `route/default_interface_monitor_other.go`
  - `route/network.go`
- 历史来源：`ffdbef28 route: avoid dumping huge route table`

## 3. 上游同步操作要求

每次同步上游后必须完成以下检查：

1. `git diff upstream/dev-next...HEAD -- route/`，确认 FIX-ROUTE-MONITOR-001 未被删除或绕过。
2. 运行最小回归：
   - `go test ./route/... -run=^$`
   - `go test ./adapter/... -run=^$`
3. 若涉及 V2bX 兼容链路，需额外验证 V2bX 联编测试。

## 4. 变更记录模板

新增/修改/移除修复时，请追加以下信息：

- 修复 ID：
- 变更类型（新增/修改/移除）：
- 影响文件：
- 变更原因：
- 验证命令：
- 验证结果：
- 审核日期：
