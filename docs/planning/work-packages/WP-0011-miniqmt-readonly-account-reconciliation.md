# WP-0011：MiniQMT 只读账户快照与启动对账

- 版本：1.0.0
- 状态：已完成并通过真实模拟盘只读验收
- 需求：REQ-2026-0004 v1.1.0、REQ-2026-0006 v1.1.0
- 阶段：4D
- UI 提案：不适用；本工作包不新增或修改页面
- 券商授权：仅 MiniQMT 有界只读账户查询
- 日期：2026-07-28

## 目标

在不产生任何券商写入的前提下，读取一个明确配置的 MiniQMT 模拟盘或实盘账户，
生成脱敏、不可变 `AccountSnapshot`，并与本地合成 Shadow 账本执行一次可恢复、
失败关闭的启动对账。

## 非目标

- 不调用 `order_stock`、`cancel_order_stock` 或任何同步/异步交易动作；
- 不启用 Paper、Live、第一笔真实订单或创建真实 `StandingMandate`；
- 不用券商账户覆盖、合并或重写 Shadow 现金、持仓和事件历史；
- 不建设 UI，不批准 UI-PROP-0003/0006/0007/0008；
- 不读取信用、期货、期权、约券或融资融券数据；
- 不提交、推送、复制凭据或保存完整账户标识。

## 允许文件

- `src/astramind_mini/trading_execution/contracts/account.py`
- `src/astramind_mini/trading_execution/domain/reconciliation.py`
- `src/astramind_mini/trading_execution/ports/account.py`
- `src/astramind_mini/trading_execution/adapters/miniqmt_account*.py`
- `src/astramind_mini/trading_execution/adapters/sqlite/`
- `src/astramind_mini/trading_execution/application/reconciliation.py`
- `src/astramind_mini/trading_execution/public.py`
- `scripts/miniqmt_account_runner.py`
- `scripts/reconcile_miniqmt_account.py`
- 聚焦测试、配置、Makefile 目标及本工作包直接相关文档

公共契约导出、配置和追加式迁移是高争用文件；实施前必须重新检查工作树，迁移编号
只能追加，不能修改既有迁移。

## 契约与架构

- `AccountSnapshot`：账户模式、查询时点、脱敏账户指纹、资金摘要、持仓、当日委托、
  当日成交、客户端/网关身份、内容哈希和已知缺口；
- `ReconciliationReport`：本地投影身份、账户快照身份、现金/持仓/未完成委托差异、
  状态、阻断原因、创建时间和内容哈希；
- Trading Execution 的账户端口只暴露领域模型，不泄漏 `xtquant`、Windows 路径、
  Token 或原始账户 ID；
- Windows runner 使用结构化 JSON 子进程协议，源码静态禁止交易、撤单和交易回调
  接口。

## 实施边界

1. 账户模式和账户 ID 通过本地秘密配置显式选择；日志、异常、SQLite、Fixture 和
   API 不出现原值，只保存不可逆指纹；
2. 只允许 `query_stock_asset`、`query_stock_positions`、`query_stock_orders`、
   `query_stock_trades` 和必要的账户状态查询；
3. 每类查询有独立超时；部分成功不发布完整账户快照；
4. 账户快照和对账报告按内容寻址只追加保存，SQLite/WAL 记录运行和发布状态；
5. 本地 Shadow 投影仍从合成起点与既有事件账本重放；券商事实仅作为对照；
6. 任一现金、证券数量、未完成委托或账户模式差异均产生明确报告，并保持未来券商
   动作阻断；
7. 重跑不得重复写入逻辑相同报告；中断后不得遗留 Windows 子进程或账户订阅。

## 命令

已新增：

```text
make miniqmt-account-reconcile
```

命令必须要求本地秘密配置中的准确账户模式和账户选择，不接收或打印命令行账户 ID。
默认只输出脱敏计数、状态与报告身份，完整本地证据写入 Git 忽略的 `var/control/`。

## 验收

1. Given 未配置账户或存在多个候选，When 启动查询，Then 失败关闭且不猜测账户；
2. Given 只读查询成功，When 发布快照，Then 模式与 `as_of` 明确，账户 ID、凭据和
   Windows 用户路径不出现在任何产物；
3. Given 任一查询超时、权限不足或返回坏 JSON，When 构建快照，Then 不发布部分成功；
4. Given 同一响应顺序变化，When 重复构建，Then 账户快照和对账报告身份稳定；
5. Given 本地与券商存在现金、持仓或未完成委托差异，When 对账，Then 差异可解释且
   `broker_actions_allowed=false`；
6. Given 源码或 runner 引用下单、撤单或交易回调，When 运行安全测试，Then 工作包
   失败；
7. Given 真实有界验收结束，When 检查系统，Then 没有券商写入、遗留子进程、订阅或
   Paper/Live 状态变化；
8. 聚焦测试、`make check`、密钥扫描、架构检查和 `git diff --check` 通过。

## 用户已批准与仍受保护

2026-07-28 用户已明确批准读取 MiniQMT 账户并新建本工作包。该批准只覆盖上述只读
查询与对账，不覆盖 Paper、Live、订单、撤单、第一份真实常设授权实例或自动执行
12% 清仓建议。

实施时如账户模式、秘密键或本机桥版本无法从安全本地配置确定，应停止真实调用并报告，
不能静默扩大到枚举或读取其他账户。

## 实施结果

- 已建立冻结且禁止额外字段的 `AccountSnapshot`、`ReconciliationReport` 及资金、
  持仓、委托、成交明细契约；账户与委托/成交身份只保存本地 HMAC 指纹；
- 已建立 MiniQMT 只读端口、四个独立超时的 Windows 查询进程、规范化与确定性身份、
  内容寻址证据存储，以及 SQLite/WAL 追加式迁移 `0002`；
- runner 只引用四个账户查询接口，安全测试静态阻断下单、撤单、订阅和交易回调；
- 本地 Shadow 继续以合成 50,000 元、空持仓为权威投影；任何资金、持仓或未完成
  委托差异都会阻断，`broker_actions_allowed` 恒为 `false`；
- `make miniqmt-account-reconcile` 已使用本地秘密配置完成一次真实模拟盘只读验收：
  发布 1 份账户快照，包含 1 个持仓、0 个当日委托和 0 个当日成交；
- 账户快照身份为
  `account-snapshot:33017fe1f60a85b45c866a070ba890bef8af3d367b5ff3afd5f0ec7848df35df`；
  对账报告身份为
  `reconciliation-report:34ca88ff5b4841f9d6e3e52d041d3124c42cfacb524e54d2f0588a2c54efdc68`；
- 对账因券商资金、持仓与合成 Shadow 起点不同而返回 `blocked`，阻断码为
  `cash_difference`、`position_difference`，且
  `broker_actions_allowed=false`；这是预期失败关闭结果，Shadow 历史未被改写；
- 真实证据与 SQLite 均未包含完整账户 ID、userdata 路径或凭据；SQLite 保持 WAL，
  查询结束后无 runner、临时目录、订阅或券商写入遗留；
- 聚焦账户/对账、既有 Shadow 与配置测试共 11 项通过；完整检查结果记录在交接文档。

WP-0011 的代码、真实只读验收和文档证据均已完成，可以关闭。对账报告保持阻断不代表
工作包未完成；它表示未来任何券商动作必须在新的受控工作包中先处理本地 Shadow 与
券商账户差异。
