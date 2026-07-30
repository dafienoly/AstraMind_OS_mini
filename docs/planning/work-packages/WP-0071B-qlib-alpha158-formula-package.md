# WP-0071B：Qlib Alpha158 保真公式包

- 版本：1.0.0
- 状态：实施中；独立复核返修与 WP-0070 v1.1 适配进行中
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5A
- UI 提案：不适用
- 前置：WP-0070 已集成；只消费其 `U0-v1`、`core-data-semantics-v1`、
  `CoreInputSnapshot`、`CoreFeaturePackageSpec` 和原始公式输出公共合同
- 所有者：Worker A / Strategy Research

## 目标

在不依赖 Qlib runtime 的前提下，本地移植规范身份
`qlib-alpha158-79633dd` 的 158 个日频特征，逐项冻结名称、顺序、公式、输入单位和
Qlib 算子边界，并用由固定 Qlib 提交生成的本地 golden fixture 证明非有限值掩码精确
一致、所有有限值的绝对/相对误差均不超过 `1e-9`。

本包只形成绑定准确 `CoreInputSnapshot` 和公式 manifest 的原始 Alpha158 公式输出，
并按 WP-0070 公共合同把内部非有限公式结果转换为稳定 `missing` 状态；不得提前承担
WP-0072 的 full/selected、缩尾、填补、标准化或中性化。

## 非目标

- 不计算 F0、Alpha101、标签、预测、Ridge、LightGBM、H20/H60、O0 或 CorePolicy；
- 不实现 full/selected、特征选择、缺失填补、缺失指示、中性化或联合包；
- 不修改 `U0-v1`、`core-data-semantics-v1`、`CoreInputSnapshot`、
  `CoreFeaturePackageSpec` 或 WP-0070 已集成的公共原始公式输出合同；
- 不新增表达式解释器、动态 `eval`、通用第二因子引擎或新的数据真相源；
- 不在生产或默认测试 runtime 安装、导入或调用 Qlib、Pandas 或 SciPy；
- 不在 runtime 访问 GitHub、下载参考源码或联网重建 fixture；
- 不调用 MiniQMT，不补采生产数据，不读取账户，不修改生产 `var/`；
- 不创建 Research Shadow、Paper、Live、StandingMandate、PortfolioTarget、
  OrderPlan、订单或券商动作；
- 不创建或修改页面、导航、组件、文案和其他 UI；

## 允许文件

- `src/astramind_mini/strategy_research/core/alpha158/**`
- `tests/unit/test_core_alpha158_*.py`
- `tests/golden/test_core_alpha158_qlib.py`
- `tests/fixtures/core/alpha158/**`
- `docs/planning/work-packages/WP-0071B-qlib-alpha158-formula-package.md`

不得修改：

- `src/astramind_mini/strategy_research/core/contracts.py`
- `src/astramind_mini/strategy_research/core/packages.py`
- `src/astramind_mini/strategy_research/core/__init__.py`
- `src/astramind_mini/contracts/**`
- `src/astramind_mini/data/**`
- `src/astramind_mini/composition.py`
- `src/astramind_mini/strategy_research/public.py`
- 根配置、锁文件、数据库迁移、前端、生产数据和其他工作包

若保真实现被证明必须改变上述共享合同、数据单位或高争用文件，停止并返回主控，不在
本包扩大范围。

## 权威来源与固定身份

唯一公式权威是 Microsoft Qlib 提交
`79633dd9506ea689e5400dea0197717b5b3d74b7` 的
`Alpha158DL.get_feature_config`。`Alpha158` handler 传入的准确配置为：

```text
{
  "kbar": {},
  "price": {
    "windows": [0],
    "feature": ["OPEN", "HIGH", "LOW", "VWAP"]
  },
  "rolling": {}
}
```

本包不采用 Qlib 的默认标签、股票池、处理器或回测配置。准确来源和本地参考生成器必须
记录下列身份：

| 来源 | SHA256 |
| --- | --- |
| `qlib/contrib/data/loader.py` | `814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb` |
| `qlib/contrib/data/handler.py` | `b621481c6009c39066c67c71390fd2bea635f56daf9f2c4e38817eff268e3232` |
| `qlib/data/ops.py` | `6f648355725a85a9f17528d864281fc065f8a4f887261a9909f7495d5db42760` |
| `qlib/data/_libs/rolling.pyx` | `58b2e418a78558135cb1ecad88bfcff68cae98b2bb2695d8d2fade8b30c5dbf1` |

将名称、公式或二者配对分别按 UTF-8、`ensure_ascii=False`、紧凑 JSON
`separators=(",", ":")` 序列化后，固定内容身份为：

```text
names_sha256  = d5f52c2d75ea900ab29f4742eeb59d9692254ba7307ad36a807012db7d680e13
fields_sha256 = 05943b7d14e82ab604fe76938465589014c6e89b51f09116a2805c59080678a3
pairs_sha256  = b1154a5b310ec5f8ead6ca064c06ae4a1121dc1c9a0d4ff7dcd00efcf20704e5
```

WP-0070 公共注册表按 158 个规范名称和统一
`feature_definition_version=1.0.0` 另固定为
`sha256:002151c6f808dc503b292caa604435f634d69672193288535f3fec504dd61c04`；
该值必须等于包规格的 `required_definition_registry_hash`。它不替代上述
Qlib 名称/公式配对哈希。

名称、顺序、展开后的准确公式字符串、上述哈希、包 ID、Qlib commit 和
`core-data-semantics-v1` 必须逐字节一致。

## 158 维规范顺序

前 13 维固定为：

```text
KMID KLEN KMID2 KUP KUP2 KLOW KLOW2 KSFT KSFT2
OPEN0 HIGH0 LOW0 VWAP0
```

后 145 维按下列 29 个族顺序展开，每个族内窗口严格为 `5, 10, 20, 30, 60`：

```text
ROC MA STD BETA RSQR RESI MAX MIN QTLU QTLD RANK RSV IMAX IMIN IMXD
CORR CORD CNTP CNTN CNTD SUMP SUMN SUMD VMA VSTD WVMA VSUMP VSUMN VSUMD
```

准确序号范围为：

| 序号 | 名称 |
| ---: | --- |
| 1–9 | `KMID KLEN KMID2 KUP KUP2 KLOW KLOW2 KSFT KSFT2` |
| 10–13 | `OPEN0 HIGH0 LOW0 VWAP0` |
| 14–18 | `ROC5 ROC10 ROC20 ROC30 ROC60` |
| 19–23 | `MA5 MA10 MA20 MA30 MA60` |
| 24–28 | `STD5 STD10 STD20 STD30 STD60` |
| 29–33 | `BETA5 BETA10 BETA20 BETA30 BETA60` |
| 34–38 | `RSQR5 RSQR10 RSQR20 RSQR30 RSQR60` |
| 39–43 | `RESI5 RESI10 RESI20 RESI30 RESI60` |
| 44–48 | `MAX5 MAX10 MAX20 MAX30 MAX60` |
| 49–53 | `MIN5 MIN10 MIN20 MIN30 MIN60` |
| 54–58 | `QTLU5 QTLU10 QTLU20 QTLU30 QTLU60` |
| 59–63 | `QTLD5 QTLD10 QTLD20 QTLD30 QTLD60` |
| 64–68 | `RANK5 RANK10 RANK20 RANK30 RANK60` |
| 69–73 | `RSV5 RSV10 RSV20 RSV30 RSV60` |
| 74–78 | `IMAX5 IMAX10 IMAX20 IMAX30 IMAX60` |
| 79–83 | `IMIN5 IMIN10 IMIN20 IMIN30 IMIN60` |
| 84–88 | `IMXD5 IMXD10 IMXD20 IMXD30 IMXD60` |
| 89–93 | `CORR5 CORR10 CORR20 CORR30 CORR60` |
| 94–98 | `CORD5 CORD10 CORD20 CORD30 CORD60` |
| 99–103 | `CNTP5 CNTP10 CNTP20 CNTP30 CNTP60` |
| 104–108 | `CNTN5 CNTN10 CNTN20 CNTN30 CNTN60` |
| 109–113 | `CNTD5 CNTD10 CNTD20 CNTD30 CNTD60` |
| 114–118 | `SUMP5 SUMP10 SUMP20 SUMP30 SUMP60` |
| 119–123 | `SUMN5 SUMN10 SUMN20 SUMN30 SUMN60` |
| 124–128 | `SUMD5 SUMD10 SUMD20 SUMD30 SUMD60` |
| 129–133 | `VMA5 VMA10 VMA20 VMA30 VMA60` |
| 134–138 | `VSTD5 VSTD10 VSTD20 VSTD30 VSTD60` |
| 139–143 | `WVMA5 WVMA10 WVMA20 WVMA30 WVMA60` |
| 144–148 | `VSUMP5 VSUMP10 VSUMP20 VSUMP30 VSUMP60` |
| 149–153 | `VSUMN5 VSUMN10 VSUMN20 VSUMN30 VSUMN60` |
| 154–158 | `VSUMD5 VSUMD10 VSUMD20 VSUMD30 VSUMD60` |

不得增加 `CLOSE0` 或 `VOLUME0`，不得把 Qlib 配置项 `LOW` 误命名为输出 `LOW5...`；
其规范输出名是 `MIN5...MIN60`。

## 公式身份

9 个 K 线形态公式为：

```text
KMID   = ($close-$open)/$open
KLEN   = ($high-$low)/$open
KMID2  = ($close-$open)/($high-$low+1e-12)
KUP    = ($high-Greater($open, $close))/$open
KUP2   = ($high-Greater($open, $close))/($high-$low+1e-12)
KLOW   = (Less($open, $close)-$low)/$open
KLOW2  = (Less($open, $close)-$low)/($high-$low+1e-12)
KSFT   = (2*$close-$high-$low)/$open
KSFT2  = (2*$close-$high-$low)/($high-$low+1e-12)
```

4 个当日价格比值为：

```text
OPEN0 = $open/$close
HIGH0 = $high/$close
LOW0  = $low/$close
VWAP0 = $vwap/$close
```

令 `d` 依次取 `5, 10, 20, 30, 60`，29 个滚动族的准确公式模板为：

```text
ROC   = Ref($close, d)/$close
MA    = Mean($close, d)/$close
STD   = Std($close, d)/$close
BETA  = Slope($close, d)/$close
RSQR  = Rsquare($close, d)
RESI  = Resi($close, d)/$close
MAX   = Max($high, d)/$close
MIN   = Min($low, d)/$close
QTLU  = Quantile($close, d, 0.8)/$close
QTLD  = Quantile($close, d, 0.2)/$close
RANK  = Rank($close, d)
RSV   = ($close-Min($low, d))/(Max($high, d)-Min($low, d)+1e-12)
IMAX  = IdxMax($high, d)/d
IMIN  = IdxMin($low, d)/d
IMXD  = (IdxMax($high, d)-IdxMin($low, d))/d
CORR  = Corr($close, Log($volume+1), d)
CORD  = Corr($close/Ref($close,1), Log($volume/Ref($volume, 1)+1), d)
CNTP  = Mean($close>Ref($close, 1), d)
CNTN  = Mean($close<Ref($close, 1), d)
CNTD  = Mean($close>Ref($close, 1), d)-Mean($close<Ref($close, 1), d)
SUMP  = Sum(Greater($close-Ref($close, 1), 0), d)/
        (Sum(Abs($close-Ref($close, 1)), d)+1e-12)
SUMN  = Sum(Greater(Ref($close, 1)-$close, 0), d)/
        (Sum(Abs($close-Ref($close, 1)), d)+1e-12)
SUMD  = (Sum(Greater($close-Ref($close, 1), 0), d)
        -Sum(Greater(Ref($close, 1)-$close, 0), d))/
        (Sum(Abs($close-Ref($close, 1)), d)+1e-12)
VMA   = Mean($volume, d)/($volume+1e-12)
VSTD  = Std($volume, d)/($volume+1e-12)
WVMA  = Std(Abs($close/Ref($close, 1)-1)*$volume, d)/
        (Mean(Abs($close/Ref($close, 1)-1)*$volume, d)+1e-12)
VSUMP = Sum(Greater($volume-Ref($volume, 1), 0), d)/
        (Sum(Abs($volume-Ref($volume, 1)), d)+1e-12)
VSUMN = Sum(Greater(Ref($volume, 1)-$volume, 0), d)/
        (Sum(Abs($volume-Ref($volume, 1)), d)+1e-12)
VSUMD = (Sum(Greater($volume-Ref($volume, 1), 0), d)
        -Sum(Greater(Ref($volume, 1)-$volume, 0), d))/
        (Sum(Abs($volume-Ref($volume, 1)), d)+1e-12)
```

代码可以从固定模板确定性展开 manifest，但不得在运行时解析或执行公式字符串。测试
必须直接比较展开后的 158 个原始 Qlib 字符串及 `pairs_sha256`，不能只比较等价数学
表达式。

## 输入与单位

每次计算只接受一个已冻结 `CoreInputSnapshot` 内、按证券隔离、按沪深共同交易日升序
排列的完整日频序列。准确字段映射为：

```text
$open   = research_open_index
$high   = research_high_index
$low    = research_low_index
$close  = research_close_index
$volume = volume_lots
$vwap   = raw_vwap_cny_per_share * research_close_index / raw_close
```

其中：

```text
raw_vwap_cny_per_share
  = amount_thousand_cny * 1000 / (volume_lots * 100)
```

约束：

- 研究 OHLC 和 VWAP 都使用 `core-data-semantics-v1` 的连续研究价格指数；
- `$volume` 固定为原始点时 `volume_lots`，单位是 100 股/手，不接受提供方原生股数；
- 新提供方必须在 Data 上下文先规范化为 `volume_lots`，Alpha158 不做提供方判断；
- 零量、缺成交额、缺原始收盘或非法原始价格时，VWAP 保持缺失，不用 epsilon 造值；
- 停牌或缺合法 Bar 的共同交易日必须保留在时间轴，因子输入保持真实缺失；不得复用
  U0 流动性资格中“成交额按 0”的专用口径；
- 每个证券的日期升序且唯一，不得删除缺失日后压缩 `Ref` 或滚动窗口；
- 计算使用 float64；fixture 固定为 little-endian `<f8`、C contiguous；
- 最大原始历史需求是 61 个共同交易日：`ROC60` 和含 `Ref(...,1)` 的 60 日滚动都
  可能访问 `T-60`。

## Qlib 算子保真

下列行为是规范，不得以“修复异常”之名改变：

1. `Ref(x,d)` 是向后 shift `d` 行；本包所有 Ref 均为非负过去引用。
2. 普通滚动包含当前行及之前最多 `d-1` 行，固定 `min_periods=1`，按 Qlib/Pandas
   行为跳过 NaN；不得改成必须凑满窗口。
3. `Std` 使用样本标准差 `ddof=1`，故只有一个有效观测时仍为 NaN。
4. `Quantile` 跳过 NaN，使用线性插值。
5. `Rank` 返回当前值在窗口有效值中的百分位秩；并列使用平均秩，当前值缺失时为 NaN。
6. `IdxMax/IdxMin` 返回窗口左侧起算的 1-based 位置；并列取最早出现者。早期窗口仍
   除以固定 `d`，所以第一行 `IMAX60=1/60`，不是 1。
7. Qlib 的 `IdxMax/IdxMin` 直接对原窗口调用 `argmax/argmin`，不先过滤 NaN；本地
   实现不得静默换成 `nanargmax/nanargmin`，窗口内 NaN 的位置结果由 golden 固定。
8. `Greater/Less` 分别是 `np.maximum/np.minimum`，不是布尔比较，NaN 会传播。
9. `>`、`<` 才是布尔比较，NaN 比较为 False；因此第一行
   `CNTP/CNTN/CNTD` 为 0，而不是 NaN。
10. `Slope/Rsquare/Resi` 对窗口位置 `x=1..d` 做带截距 OLS，只跳过缺失 y，但保留
    x 的时间缺口；`Resi` 是当前 `x=d` 的残差。实现应复刻固定 Cython 的递推和
    浮点运算次序，不得换成 `polyfit`。
11. `Rsquare` 还将窗口样本标准差满足
    `np.isclose(std, 0, atol=2e-5)` 的结果置 NaN。
12. `Corr` 使用成对完整观测和样本协方差/标准差；至少需要两个有效配对。Qlib 另对
    左右序列各自的滚动样本标准差应用 `atol=2e-5` 近零屏蔽。
13. `Log` 是自然对数，`Abs` 是逐元素绝对值。
14. 只使用公式中逐字写出的 `1e-12`；不得增加全局安全除法 epsilon。
15. 零分母按 IEEE 754 形成 NaN 或正负 Inf。内部公式缓冲和 golden 必须保留并核对
    该分类；进入 WP-0070 `CoreRawFeatureRowDraft` 前，本包必须将所有非有限结果转换
    为 `availability_state=missing`、`value_raw=None` 和稳定原因码
    `alpha158_non_finite_formula_result`。有限结果转换为 `observed`；Alpha158 不产生
    `not_applicable`。不得把 NaN/Inf 写入公共合同或推迟到 WP-0072 才处理。
16. Qlib 没有把当前输入缺失统一覆盖回输出缺失；部分滚动列可能在当前行缺失时仍有
    数值。不得增加统一“当前行有缺失则 158 列全空”的遮罩。

必须有聚焦断言覆盖：

```text
ROC60：前 60 行缺失，第 61 行才可能有效
MA60：第一行即可有效
STD60：至少两个有效观测
RANKd：第一有效行等于 1
IMAXd/IMINd：第一行等于 1/d
CNTP/CNTN/CNTD：第一行均为 0
SUMP/SUMN/SUMD：首个差分为 NaN
VMA：当前 volume=0 时分母是 1e-12，可能产生极大有限值
CORD：前一日 volume=0 时内部可能出现 Inf 或 NaN
```

## 本地模块边界

建议在唯一拥有目录内按责任拆分：

```text
strategy_research/core/alpha158/
  __init__.py
  definitions.py
  inputs.py
  rolling.py
  regression.py
  calculator.py
```

- `definitions.py` 只拥有固定模板、确定性展开、158 维 manifest 和固定哈希；
- `inputs.py` 只拥有单证券日序列、共同日历、六输入字段与原始结果结构；
- `rolling.py` 只实现本包需要的 NumPy 滚动、Rank、Idx 和 Corr 语义；
- `regression.py` 只复刻 Qlib Cython 的 Slope/Rsquare/Resi；
- `calculator.py` 只按 manifest 固定顺序组装 158 列，把内部非有限结果按本文规则
  转为 `CoreRawFeatureRowDraft`，并复用 WP-0070 builder 绑定
  `CoreInputSnapshot`、包身份和内容哈希；
- 子包 `__init__.py` 是唯一公开入口；不修改上层 `core/__init__.py`；
- 不建立跨 F0/Alpha101 的共享 `utils.py`、第二注册表或通用表达式引擎。

原始结果必须至少绑定：

- `core_input_snapshot_id` 和其内容哈希；
- `package_id=qlib-alpha158-79633dd`；
- `data_semantics_version=core-data-semantics-v1`；
- 证券、共同交易日、158 个规范名称和 shape；
- manifest `pairs_sha256`；
- 内部 float64 数值和 NaN/+Inf/-Inf 掩码；
- 公开 `CoreRawFeatureEnvelope` 的 `observed/missing` 状态、稳定原因码和确定性内容哈希。

## Golden fixture

本包提交一个至少 `3 只证券 × 75 个共同交易日 × 158 列` 的本地 golden。75 日既
覆盖 61 日最长原始回看，又保留窗口成熟后的滚出样本。

三只合成证券必须共同覆盖：

- 趋势、反转、平盘段、重复收盘和重复高低点；
- 并列 Rank、并列 Idx 最大/最小且最早并列在窗口内；
- 一整行停牌/缺 Bar 的 NaN、窗口开头/中间/当前行缺失；
- `high==low` 的一字价格；
- 独立零量、连续零量、零量后恢复和非零量后归零；
- 常量和近常量序列，以及相关/RSQR `2e-5` 阈值两侧；
- 正常、零和缺失分母，但不把非法零价格伪装为生产合法 Bar。

每个 158 列在最长 warm-up 后必须至少出现一个有限期望值；若某一专门边界只应产生
非有限值，另有明确逐列断言。Alpha158 不消费行业，不为满足跨包 Golden 的行业缺层
用例而增加虚假行业输入；行业缺层由 Alpha101 或后续共享跨包验收承担。

Fixture 目录至少保存：

```text
tests/fixtures/core/alpha158/
  provenance.json
  manifest.json
  inputs.npy
  expected.npy
  expected_nonfinite_mask.npy
```

`provenance.json` 必须记录：

- Qlib commit 和四个源文件 SHA256；
- 参考生成器版本；
- Python、NumPy、Pandas、SciPy、Cython、编译器和平台版本；
- 输入 dtype、字节序、内存顺序、证券顺序和日期顺序；
- 输入、manifest、预期输出和非有限掩码的逻辑内容哈希；
- 生成命令及“只允许在隔离参考环境显式运行”的说明。

固定 Qlib 提交只声明 `pandas>=1.1`，没有锁定准确 Pandas/NumPy 版本，因此
`provenance.json` 必须额外锁定参考生成环境。生产和默认测试只读取已提交 fixture，
不得安装 Qlib 或联网。若需重生成，必须在仓库外隔离环境中从已校验的固定提交显式
执行，并在 diff 中同时审查所有输入、输出、掩码和 provenance 哈希变化。

逻辑哈希前统一将数组转换为 little-endian float64、C contiguous，并把所有 NaN
规范为固定 quiet-NaN bit pattern；正负 Inf 保留符号。fixture 容器本身的时间戳或
压缩元数据不得进入内容身份。

## 数值和逐字节门禁

必须逐字节一致：

- 158 个名称、顺序和展开后的原始 Qlib 公式字符串；
- 包 ID、Qlib commit、数据语义版本及三个 manifest SHA256；
- fixture 输入的证券/日期顺序、shape、dtype 和逻辑内容哈希；
- 每个结果单元的 finite/NaN/+Inf/-Inf 分类掩码；
- 同一输入重跑、整批/分块计算和追加未来数据后的既有前缀规范字节。

所有有限值逐项使用：

```python
np.testing.assert_allclose(
    actual_finite,
    expected_finite,
    rtol=1e-9,
    atol=1e-9,
)
```

任何列超差必须定位到准确证券、日期、序号、名称、公式和算子；不得扩大容差掩盖错误。
Rank、Idx、CNTP/CNTN/CNTD 等离散或有理结果还必须直接相等。

## 点时、缺失和未来泄漏

- 只消费 `CoreInputSnapshot` 冻结且 `available_at <= cutoff_at`、
  `market_date <= decision_date` 的完成日数据；
- 不读取当前会话、形成中分钟、未封存 Tick 或截止后修订；
- 不使用 Qlib handler 的默认标签；其中负 Ref 属于未来标签，不是 Alpha158 特征；
- 不使用快照终端复权因子构造研究 OHLC 或 VWAP；
- 不删除停牌/缺 Bar 的共同交易日，不前向/后向填充，不使用 `center=True`；
- 不把多个证券拼接后滚动，不让证券排序影响任一证券数值；
- 对任意输入前缀附加任意未来 10 日后，原前缀名称、非有限掩码、有限值和规范内容
  字节必须完全不变；
- 证券重排只能重排结果，改变某一证券不得改变其他证券；
- 输入日期重复、逆序、缺共同交易日、字段长度或 shape 不一致时失败关闭。

## 验收

1. Given 固定 manifest，When 确定性展开，Then 维数、唯一名称数均为 158，名称、
   字段和配对哈希分别等于本文固定值。
2. Given 75 日 golden，When 本地 NumPy 实现计算，Then非有限掩码逐单元一致，所有
   有限值均在绝对/相对 `1e-9` 内，离散结果直接相等；公开 envelope 中不存在
   NaN/Inf，所有对应单元均为稳定 `missing`。
3. Given 未满 60 日的前缀，When 计算各窗口，Then `min_periods=1`、Ref warm-up、
   `ddof=1` 和固定窗口除数不会被误写成满窗规则。
4. Given 并列、NaN、零量、连续零量、常量和阈值两侧输入，When 计算 Rank、Idx、
   Greater/Less、Corr、RSQR 和量价族，Then 结果与固定 Qlib quirks 一致。
5. Given 一整行停牌缺失，When 计算，Then 时间轴不压缩、U0 成交额零填充规则不被
   写回因子输入，且 Qlib 允许产生值的滚动列不被统一遮罩。
6. Given 同一证券同一输入，When 整批计算、按安全块计算或重复计算，Then 规范输出
   内容身份完全一致。
7. Given 已计算前缀，When 追加未来数据，Then 既有前缀逐字节不变；截止后输入和
   Qlib 默认未来标签均有负向测试证明不可进入特征。
8. Given 多证券输入，When 改变证券顺序或只修改一只证券，Then 数值只随对应证券
   重排或变化，不发生跨证券窗口污染。
9. Given 输入单位从手误换为股、缺日期、日期重复/逆序或 shape 不一致，When 调用，
   Then 使用稳定原因码失败关闭，不能静默换算或压缩。
10. Given 默认测试环境，When 导入和运行 Alpha158，Then 导入图中不存在 Qlib、
    Pandas、SciPy、GitHub、MiniQMT、Portfolio & Risk 或 Trading Execution。

## 检查

默认受影响检查必须在 90 秒内完成，不得隐含安装 Qlib、联网、重建 fixture、全历史
计算或生产数据扫描：

```text
uv run pytest tests/unit/test_core_alpha158_*.py tests/golden/test_core_alpha158_qlib.py
uv run pytest tests/unit/test_core_data_semantics.py tests/unit/test_architecture.py
uv run ruff check src/astramind_mini/strategy_research/core/alpha158 tests/unit/test_core_alpha158_*.py tests/golden/test_core_alpha158_qlib.py
uv run mypy src/astramind_mini/strategy_research/core/alpha158 tests/unit/test_core_alpha158_*.py tests/golden/test_core_alpha158_qlib.py
make docs-check
git diff --check
```

参考 fixture 重生成属于显式长任务，不进入上述默认检查。

## 交接

完成后向主控交付：

- 158 维 manifest、三个固定哈希和逐列 golden 对齐摘要；
- fixture 输入/输出/非有限掩码/provenance 的内容身份；
- `1e-9` 最大绝对误差、最大相对误差及其证券/日期/列定位；
- 前缀不变、分块等价、证券隔离、输入单位和未来泄漏负测结果；
- 默认检查总耗时，确认低于 90 秒；
- 明确确认未修改 WP-0070 公共合同、未使用 runtime Qlib/GitHub/MiniQMT，
  未接触生产数据、账户、交易、Paper 或 Live。

主控复核后才可由 WP-0072 消费本包已符合 WP-0070 三态公共合同的原始输出，并实施
full/selected、缩尾、填补、标准化和中性化。
