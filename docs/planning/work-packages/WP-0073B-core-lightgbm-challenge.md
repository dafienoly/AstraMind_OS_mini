# WP-0073B：核心 H20/H60 LightGBM 有预算挑战

- 版本：1.0.0
- 状态：已授权，依赖门等待 WP-0074A 的槽位 manifest
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5C
- UI 提案：不适用
- 所有者：后续非线性模型工作树 / Strategy Research

## 目标

只消费 WP-0074A 从真实 Ridge C2/O0 开发证据冻结的最多四个父级槽，在 H20/H60 各自
预算内训练固定八模板 LightGBM，形成严格向前 OOF、季度模型、安全制品、绝对收益
校准和相对同配置 Ridge 的配对证据输入。

本包不重选父级、不扩大搜索空间、不宣布决赛资格。WP-0074B 只有在准确 C2 增量
bootstrap 第 10 百分位大于 0 后，才可让每周期最多一个 LightGBM 进入最终比较。

## 启动门

1. WP-0073A 已集成，标签、训练计划、Ridge OOF 和校准 API 已冻结；
2. WP-0074A 已集成并发布准确 `CoreLightGBMSlotManifest`；
3. 每个槽绑定一个周期、一个 Ridge 父级、准确特征视图、开发折和 C2/O0 证据；
4. 主控已单独提交并锁定 `lightgbm==4.6.0`，工作树从该最新主线建立；
5. 当前 CPU 环境通过重复训练确定性 preflight。

槽为空不是阻断：对应家族明确 `slot_closed`。manifest 缺失、篡改、父级不兼容或超过
四槽时整个请求失败关闭。

## 非目标

- 不重新计算标签、特征、selection、Ridge、O0 或 C2 父级胜负；
- 不训练未获槽位的 full/selected/联合配置，不做随机、Bayesian 或扩大网格搜索；
- 不用 HistGradientBoosting、XGBoost、神经网络或 GPU 实现替代；
- 不用诊断种子换赢家，不在 2023～2025 回放途中递补失败模板；
- 不实现 CorePolicy、晋级决定、Research Shadow、UI、MiniQMT、Paper/Live 或订单；
- 不运行生产快照训练或激活真实候选。

## 允许文件与依赖

- `src/astramind_mini/strategy_research/core/lightgbm_challenge/**`
- `tests/unit/test_core_lightgbm_*.py`
- `tests/golden/test_core_lightgbm_challenge.py`
- `tests/fixtures/core/lightgbm/**`
- 本工作包及直接追踪状态

不得修改 `pyproject.toml`、`uv.lock`、WP-0073A/0074A 所有目录、共享合同、三个因子
包、Data、Portfolio & Risk、Trading Execution、`composition.py`、生产 `var/` 或
前端。LightGBM 上游正式版本和参数以
[LightGBM v4.6.0 发布记录](https://github.com/lightgbm-org/LightGBM/releases/tag/v4.6.0)
与[官方参数文档](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html)为审计来源；
运行时不访问网络。

## 制品和身份

本子包拥有：

- `CoreLightGBMTrainingSpec`；
- `CoreLightGBMTemplate`；
- `CoreLightGBMArtifactManifest`；
- `CoreLightGBMOutOfFoldBatch`；
- `CoreLightGBMChallengeSet`。

每个制品绑定槽位、父级 Ridge、周期、特征列及顺序、训练折、模板、主/诊断种子、
LightGBM/NumPy 版本、CPU/线程和确定性参数、`best_iteration`、模型文本哈希、预测
哈希、校准器和代码身份。模板、环境或父级任何变化创建新 lineage，不能覆盖旧证据。

只使用 LightGBM 原生文本模型的规范 UTF-8 表示或经证明等价的无代码执行格式；禁止
pickle。序列化后重新加载，必须复核 feature names、列数、objective、全部固定参数、
`best_iteration` 和 golden 预测。文本中的非语义构建信息必须规范化，但不得删除影响
预测的树、阈值、缺失方向或特征映射。

## 固定槽位和模板

每个 H20/H60 最多四槽：

1. 最佳 F0 Ridge 父级；
2. 最佳 Alpha158 Ridge 父级；
3. 最佳 Alpha101 Ridge 父级；
4. 最佳已允许 selected 联合 Ridge 父级。

槽位顺序固定。缺少合格父级时保留关闭状态，不用次优、其他包或 full 联合补位。

每槽恰好八个模板，由以下笛卡尔积生成：

- `max_depth ∈ {3, 5}`，对应 `num_leaves ∈ {7, 31}`；
- `min_data_in_leaf ∈ {50, 200}`；
- `feature_fraction ∈ {0.7, 1.0}`。

共同参数：

- `objective=regression_l2`、`metric=l2`；
- `lambda_l2=1`、`lambda_l1=0`；
- `learning_rate=0.03`、`num_boost_round=500`；
- `bagging_fraction=0.8`、`bagging_freq=1`；
- `verbosity=-1`、`deterministic=true`、`force_col_wise=true`；
- `num_threads=1`；
- 50 轮早停并保存准确 `best_iteration`。

不得同时设置 `force_row_wise`。别名必须规范成上述主参数名后再计算身份，避免同义参数
制造重复候选。

## 种子与胜者

- 主种子：`20260729`；
- 稳定性诊断种子：`20260730`、`20260731`；
- 所有 LightGBM 随机入口显式派生并保存，包括 data/feature/bagging seed；
- 主种子按开发期 OOF 形成八模板候选；
- 诊断种子只在主种子模板冻结后重训该模板，报告预测相关、RankIC 和 C2 稳定性输入；
- 诊断种子更优或主种子失败都不能换模板；主种子失败则该槽失败关闭。

模板最终胜负由 WP-0074B 使用主种子 C2/O0 证据决定。训练损失、early stopping
iteration 或单独 RankIC 只能诊断。

## 训练、OOF 与校准

完全复用 WP-0073A 的：

- H20/H60 点时标签；
- 五年滚动主窗与扩展窗诊断；
- 至少三个、每个不少于 26 周的严格向前 OOF 验证块；
- 日期等权、日期内证券等权；
- 季度重训和 2023～2025 历史模型版本规则；
- 十桶 PAVA 绝对收益校准及 156 周、每桶 30 样本、方向和到期门。

不得复制这些算法或在 LightGBM 子包中建立第二版本。每个 OOF 折从训练块末端保留
最后 26 个周度截面作为早停集，更早数据用于拟合；整个后续 OOF 验证块保持未见并用于
评分，不能把 OOF 行拿来决定 `best_iteration`。若训练块不足以同时保留拟合和早停区间，
该折失败关闭。模板冻结后季度生产重训使用开发期
`best_iteration` 的折间中位数（偶数取较小的中间整数），不再用未来验证集早停。

## 相对 Ridge 挑战证据

本包发布与父级 Ridge 完全相同决策日和证券范围的预测及校准，不做 pairwise 删除：

- 候选特有缺失使对应挑战失败；
- 系统性无效周只能由 WP-0074A 的共同排除账本同时排除；
- 标签、特征、成本版本、O0 和起始资本必须相同；
- H20 使用 4 周、H60 使用 12 周的配对圆形移动区块；
- 重采样 10,000 次，种子由候选证据 ID、父级证据 ID、周期和成本版本生成。

WP-0074B 计算 `ΔCAGR` 分布并要求 LightGBM 相对同配置 Ridge 的第 10 百分位严格大于
0。未通过的候选永久保留研究证据，但不能成为决赛者。

## Golden 与负向证明

fixture 覆盖两个周期、四槽、八模板、三个种子、三个 OOF 验证块，并包括：

- 槽位关闭、超预算、父级错配和 manifest 篡改；
- 模板参数顺序/别名、`num_leaves` 与深度错配、同时 force row/col；
- 早停、`best_iteration` 折中位数、季度重训和历史模型不可回填；
- 主种子失败、诊断种子更优、模板动态递补；
- 重复训练、模型文本规范化、重新加载和预测哈希；
- 未来数据追加后旧 OOF、模型、校准和身份不变。

golden 固定 LightGBM 4.6.0、CPU 单线程输入、参数、`best_iteration`、规范模型哈希和
预测；预测使用 `atol=rtol=1e-10`，其他身份/状态/顺序/参数/哈希精确相等。若支持
平台无法复现，必须明确 `environment_nondeterministic`，不能放宽容差或改用别的模型。

默认小 fixture 在 90 秒内完成；四槽×八模板×三种子×完整五年属于显式慢测。

## 验收

1. 每周期不超过四槽，每槽恰好八模板，父级和列身份不能被替换。
2. H20/H60、主/诊断种子、OOF、季度模型和校准制品完全分离。
3. LightGBM 4.6.0、单线程和确定性参数通过重复训练、重载与 golden 预测。
4. 主种子唯一决定模板候选，诊断种子不能换赢家，失败途中不能动态递补。
5. 当前模型不能回填历史；未来数据和后续季度不能改变旧制品。
6. 相对 Ridge 证据同窗、同成本、同 O0，不允许候选特有 pairwise 删除。
7. 导入图不包含 MiniQMT、账户、Portfolio & Risk、Trading Execution、前端或网络。

## 检查

```text
uv run pytest tests/unit/test_core_lightgbm_*.py \
  tests/golden/test_core_lightgbm_challenge.py -q
uv run pytest tests/unit/test_core_modeling_*.py tests/unit/test_architecture.py -q
uv run ruff check src/astramind_mini/strategy_research/core/lightgbm_challenge \
  tests/unit/test_core_lightgbm_*.py tests/golden/test_core_lightgbm_challenge.py
uv run mypy --strict src/astramind_mini/strategy_research/core/lightgbm_challenge
make docs-check
git diff --check
```

## 授权与交接

主控复核固定预算、父级身份、确定性、OOF、早停、种子、模型安全和负测后集成，再释放
WP-0074B 最终比较。本包完成只表示非线性挑战证据可复算，不表示 LightGBM 胜出、候选
晋级、生产激活或获得交易权限。

本授权不包含生产训练、新 UI、生产补采、MiniQMT、Research Shadow 实际运行、账户、
StandingMandate、Paper/Live 或订单。
