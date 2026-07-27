# 界面提案与批准流程

用户要求所有重要界面实施前先看到示意图。这个流程只保留必要的视觉决策，不建立繁重审批体系。

## 什么时候需要新提案

- 新页面或一级视图；
- 导航变化；
- 重要布局变化；
- 新审批或交易工作流；
- 新共享视觉语言；
- 重要响应式行为变化；
- 重要动态图表及其时间控制方式。

错别字、不可见重构或不改变布局的小型无障碍/渲染修复通常可以沿用已批准版本。

## 目录格式

```text
docs/ui/proposals/
  0001-shell-market-dashboard/
    proposal.md
    schematic-v0.2.svg
    schematic-v0.2.png
  0002-market-relative-rotation-map/
    proposal.md
    schematic-v0.1.svg
    schematic-v0.1.png
    motion-storyboard-v0.1.svg
    motion-storyboard-v0.1.png
  0010-full-interface-atlas/
    proposal.md
    interface-atlas-v0.2.svg
    interface-atlas-v0.2.png
  0011-industry-lifecycle-research/
    proposal.md
    structure-map-v0.1.svg
    structure-map-v0.1.png
    industry-ranking-v0.1.svg
    industry-ranking-v0.1.png
```

## 提案必备内容

- 提案编号和版本；
- 状态；
- 页面与唯一任务；
- 目标用户和要回答的问题；
- 视觉示意图；
- 可见数据；
- Loading、Empty、Stale、Blocked、Error、Disconnected；
- 主要动作或只读边界；
- 桌面和窄屏行为；
- 明确不做；
- 待确认问题；
- 批准记录。

## 状态

- `draft`：内容尚不完整；
- `awaiting_user_approval`：已经可以评审；
- `approved`：准确版本可以实施；
- `superseded`：保留历史，但不能再实施。

沉默、对其他阶段的批准或产品需求批准，都不等于视觉批准。

用户可以在一句话中明确批准多个准确提案版本。总览图使用 `draft` 状态作为索引，便于一次审阅，但批准仍分别记录到每个功能提案；批准总览本身不能推定批准其中全部界面。

## 批准记录

```text
approved_version:
approved_by:
approved_at:
source_message:
```

只有用户明确接受该视觉版本，才能填写。

## 实施与复核

工作包必须写明 UI 提案编号和版本。实现可以为响应式或无障碍微调间距，但不能在没有新提案的情况下改变信息层级或视觉方向。

完成后：

1. 截取桌面和窄屏真实界面；
2. 与已批准示意图比较；
3. 列出有意差异；
4. 核验加载、空、陈旧、阻断和错误状态；
5. 若发生实质漂移，重新提交视觉版本。
