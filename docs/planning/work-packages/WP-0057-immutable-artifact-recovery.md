# WP-0057：不可变制品完整性修复与快照恢复

- 版本：1.2.0
- 状态：已完成
- 需求：REQ-2026-0004 v2.8.0
- 阶段：2A、2F、7
- UI 提案：不适用
- 所有者：Data

## 目标

消除可变工作文件与内容寻址制品共享 inode 的发布路径，增加字节哈希、行数、主键和
日期范围复核，并以可审计的新版本恢复 2026-07-29 当前快照。

## 非目标

- 不修改行情公式、研究结果或模型阈值；
- 不静默改写旧清单、旧哈希或旧快照；
- 不连接 MiniQMT 账户，不执行 Paper/Live 或订单；
- 不在并行 worktree 中直接修改主工作区 `var/`。

## 允许文件

- `src/astramind_mini/data/adapters/filesystem.py`
- `src/astramind_mini/data/application/raw_records.py`
- `src/astramind_mini/data/application/snapshot_reconciliation.py`
- 新建的单一用途恢复模块与命令
- 对应 Data 单元/集成测试
- 本工作包实施结果

## 高争用边界

- 不修改 `composition.py`、公共契约、需求索引或阶段计划；
- 若必须修改数据公共契约，先返回主控对话集成，不在分支自行扩大范围。

## 验收

1. Given 可变工作文件继续追加，When 已发布数据集完成，Then 两者 inode 不同且旧制品
   字节哈希保持不变。
2. Given 发布前后的哈希、行数、主键或日期范围任一不一致，When 尝试提交，Then
   发布失败关闭且当前指针不变。
3. Given 已污染的 2026-07-29 制品，When 执行显式恢复，Then 旧身份保留审计记录，
   新版本和新快照可复算并原子切换。
4. 默认测试使用临时目录，不读取或修改用户生产 `var/`。

## 受保护动作

恢复命令开发完成后，主工作区真实快照重发由主控对话单独执行和复核；不包含提供方
联网或券商动作。

## 实施结果

- `FilesystemDatasetStore` 不再使用硬链接；文件先复制到同级临时目录，复核后才原子
  暴露完整数据集目录；
- 发布前后复核每个文件的 SHA-256；真实 Parquet 额外复核总行数、主键唯一性和
  主键日期最小值/最大值与清单精确一致；
- 数据集和 `DataSnapshot` 指针切换前再次读取清单、复核制品，并拒绝
  `st_nlink > 1` 的历史硬链接制品；
- 新增本地恢复服务和 `scripts/recover_immutable_snapshot.py`。命令只接受显式
  `--data-root`、`--control-db` 与 JSON 计划，并要求
  `--apply REPUBLISH_IMMUTABLE_SNAPSHOT`；不包含提供方或券商调用；
- 恢复保留旧目录和旧清单，产生新数据集版本、新快照及内容寻址恢复报告，再以
  `expected_snapshot_id` 比较交换当前指针；
- 单元/集成测试全部使用临时目录，覆盖 inode 独立、源文件后续改写、复制中断、
  哈希/行数/主键/日期失败关闭、旧身份保留和新快照原子切换。

恢复计划格式：

```json
{
  "base_snapshot_id": "snapshot:sha256:...",
  "datasets": {
    "daily_market": {
      "daily-market-2026.parquet": "/absolute/verified/source.parquet"
    }
  }
}
```

## 真实恢复结果

- 用户于 2026-07-30 明确批准主控执行真实快照恢复；
- 基础快照为
  `snapshot:sha256:6970c8c222e4855c92c7b8acb4edeb598c1cef87701a2dae8bd40979ef8aa5c9`；
- 首次恢复在切换指针前因 `daily_tradability` 主键不唯一而失败关闭。核验发现
  3 条更名记录把下一名称起始日同时作为上一名称的闭区间结束日；
- 修复名称区间为 `next_start - 1 day` 后，仅重建
  `security_name_history` 和 2026 年 `daily_tradability`。2026 年制品从
  803,888 行收敛为 803,885 行，全历史为 17,773,439 行，主键唯一数同为
  17,773,439，名称区间重叠为 0；
- 18 个受影响数据集、266 个制品完成重新发布并原子切换到
  `snapshot:sha256:ed77dfcb0a8082d4acbdcab86192d51405a8ba0315bfa1d9e8fc9228b37aa073`；
- 发布后逐文件复核恢复源与新制品 SHA-256，一致性错误为 0；全部新制品
  `st_nlink = 1`，数据集当前指针与新快照一致；
- 旧快照和旧数据集身份完整保留。恢复报告位于
  `var/data/recoveries/07704bbddf627f65d8bafb876e587aa1fd6135544bb18a34992648ed0965647d/report.json`；
- 全过程提供方网络调用为 0，券商动作授权为 `false`。

WP-0057 已解除 WP-0059 真实 ETF 历史补采和 WP-0062 可信快照前置；两者仍须分别
满足自身的提供方、点时数据和模型证据门。
