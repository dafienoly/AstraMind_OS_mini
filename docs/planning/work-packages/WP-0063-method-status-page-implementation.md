# WP-0063：系统“方法与状态”页面实施

- 版本：1.0.1
- 状态：已完成
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

## 实施结果（2026-07-30）

- 在唯一 AppShell 内增加稳定的 System 二级导航和 `/system/method-status` 路由；
- 页面固定展示五类模型索引、V1/V2 定义、预测目标、五段方法谱系尺、准确业务原因、
  已发布时间语义和默认折叠的技术详情；
- 只消费既有 `/api/market/model-status`。接口未发布的数据日期、行情/接收时间、训练/
  证据截止和输入版本准确显示“尚无已发布记录”，没有由本机时间或其他投影推断；
- 覆盖 Loading、Empty、Disconnected、Blocked、Error、`fallback_v1`、
  `unvalidated_v2`、`active_v2`、制品异常及刷新失败保留上次成功投影；
- 状态族重复、未知枚举、无效时间或只读边界异常均失败关闭，不显示绿色健康状态；
- 页面只有模型选择、刷新、查看数据与作业和展开技术详情，没有训练、激活、策略晋级、
  MiniQMT、Paper、Live、组合或订单动作。

聚焦验收：

```text
pnpm --filter @astramind/web test
  27 files / 104 tests passed
pnpm --filter @astramind/web lint
  passed
pnpm --filter @astramind/web typecheck
  passed
pnpm --filter @astramind/web build
  passed
ASTRAMIND_E2E_BASE_URL=http://127.0.0.1:5176 \
  pnpm exec playwright test tests/e2e/method-status.spec.ts
  1 passed
```

提案对照截图：

- [桌面 1440px](../../ui/proposals/0013-method-status/actual-desktop-1440x1000.png)
- [窄屏 390px](../../ui/proposals/0013-method-status/actual-mobile-390x844.png)

实际页面保留批准提案的“五类索引 + 方法谱系尺 + 原因/时间 + 折叠技术详情”层级和
蓝/赭/深红状态语义。有意差异只有两项：顶部沿用已批准且持续挂载的唯一 AppShell，
不复制示意图中的独立深色壳层；示意图中的样例日期改为准确缺失文案，因为现有公共
状态契约没有发布对应字段。窄屏索引和谱系尺使用局部横向滚动，页面本身没有横向溢出。
