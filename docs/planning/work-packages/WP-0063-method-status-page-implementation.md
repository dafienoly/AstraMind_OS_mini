# WP-0063：系统“方法与状态”页面实施

- 版本：1.0.0
- 状态：已批准实施
- 需求：REQ-2026-0003 v1.9.0、REQ-2026-0008 v2.2.1
- 阶段：6I、7
- UI 提案：UI-PROP-0013 v0.1（`approved`）
- 所有者：UI；只读消费 Market Regime 公共状态

## 目标

在既有“系统”一级入口内实现“方法与状态”二级页面，让用户看清五类市场模型当前
使用 V1 还是 V2、停在哪一道数据/训练/证据/激活门，以及为什么准确回退 V1。

## 复用与边界

- 复用 `/api/market/model-status`、既有 `model-evidence` 类型/客户端和统一业务文案；
- 复用唯一 AppShell、顶部五入口、路由 Loading 和折叠 `TechnicalDetails`；
- 页面缺少某个日期或证据字段时显示“尚无已发布记录”，不得从当前日期、文件时间或
  其他模型推断；
- 本包不扩展训练 API、激活 API、模型契约或生产 `var/`；若现有只读 API 无法表达
  必需事实，以准确 Empty/Blocked 显示并返回主控另立后端包，不在 UI 中补造。

## 允许文件

- `apps/web/src/system-method-status/**`
- `apps/web/src/App.tsx`
- `apps/web/src/app-shell/AppShell.tsx`
- `apps/web/src/app-shell/navigation.ts`
- `apps/web/src/app-shell/types.ts`
- `apps/web/src/operations/**` 中仅限 System 二级导航衔接
- `apps/web/src/business-language/**` 中仅限新增方法状态业务文案
- 既有前端样式文件、对应 Vitest 和单一 E2E 流程
- 本工作包实施结果和提案对照截图记录

`composition.py`、后端公共契约、模型训练/激活模块、数据发布、根配置和锁文件不在
允许范围。共享前端壳层由本包单独占用，不与其他 UI 工作包并行修改。

## 可见行为

1. System 二级导航稳定显示“数据与作业 / 方法与状态 / 执行与恢复”，仍只有五个
   一级入口。
2. 五类模型索引显示准确业务名称、当前方法、状态和最近已发布截止；选择后展示
   “规则 V1 → 数据门 → 生产训练 → 样本外证据 → 只读激活”谱系尺。
3. 展示 V1/V2 定义、预测目标、可用时间语义、业务缺口和准确回退原因。
4. 内部枚举、完整身份、原因码和输入版本只进入默认折叠的技术详情。
5. 页面没有“立即训练”“强制激活”“晋级策略”“下单”或券商连接动作。

## 验收

1. Given 五类状态正常返回，When 打开 `/system/method-status`，Then 桌面和窄屏均
   符合 UI-PROP-0013 v0.1 的信息层级，并可选择每个模型查看谱系。
2. Given `fallback_v1`、`unvalidated_v2`、`active_v2` 或 `blocked`，When 页面渲染，
   Then 显示对应中文业务解释且不把未知/阻断显示为绿色健康。
3. Given API Loading、Empty、刷新失败、断开或状态损坏，When 页面读取，Then 保留
   稳定布局、显示准确恢复入口；已有成功投影在局部刷新失败时继续可读并降级标记。
4. Given 用户展开技术详情，When 查看原始身份，Then 完整哈希/枚举可见；默认状态
   下主页面不裸露内部代码。
5. Given 任意状态，When 检查可交互控件，Then 不存在模型训练、激活、策略晋级、
   `PortfolioTarget`、`OrderPlan`、MiniQMT、Paper、Live 或订单动作。
6. Vitest 覆盖五类选择、状态文案、技术详情和失败路径；Playwright 覆盖桌面与
   390px 窄屏；保存真实截图并记录与批准示意图的有意差异。

## 完成定义

行为、路由、响应式布局、Loading/Empty/Blocked/Error/Fallback/Active 状态、局部
刷新恢复、文档、Vitest、浏览器流程和提案截图对照全部完成后，才能把本包标记完成。

