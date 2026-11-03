---
name: auto-solidworks-lite
description: 根据文字或图片创建或修改可编辑的 SolidWorks 模型，并完成保存重开、导出和结果复核；仅在用户要求 SolidWorks/CAD 自动化时使用。
---

# Auto SolidWorks Lite

目标是交付可编辑的原生模型和可核查的结果证据。图片只提供外观线索；没有比例时记录估计值，不声称精确复刻、制造或配合已经验证。

## 最短工作流

1. **确定路线**：普通零件优先使用本技能的 `scripts/local_sw.py`；孔槽、螺纹、圆角/倒角、装配、工程图、复杂曲面或 FEA 只读取对应的上游子技能/参考文件。只为当前任务读取一个相关分支，不预加载全部 CAD 文档。
2. **前置检查**：确认本地 SolidWorks 自动化环境可用，并定位 `solidworks-automation` 上游目录。可通过 `AUTO_SOLIDWORKS_UPSTREAM` 显式指定；未设置时使用默认的 Codex skill 目录。原生写入前运行上游 `scripts/sw_preflight.py` 或 `cad_studio.py doctor`。缺依赖时说明用途，安装前取得用户授权。
3. **建模**：先写出关键尺寸、假设和实体关系，再使用参数和几何约束建模。不要用批量 Fix 代替设计意图；关键尺寸不确定且会改变拓扑时先澄清。
4. **交付检查**：保存原生文件，重开并重建；确认草图被目标特征消费，至少试改并恢复一个真实驱动尺寸。按需要导出 STEP/STL，并生成等轴测、前、俯、右视图。
5. **汇报状态**：报告输出路径、SolidWorks 版本、实际尺寸与估计项、重开/重建结果、导出结果和人工复核项。任何未知、失败或未检查项都保留为 `review_required`，不宣称完成。

## 安全边界

- 只创建和清理本轮登记的新文档；不修改或关闭用户已有文档。
- 不强杀未知 SolidWorks 进程，不开放端口或远程 DCOM，不把 COM 失败直接解释为安装损坏或必须管理员运行。
- 注册修复只允许使用 SolidWorks 官方 `/regserver`，先备份并在用户授权后执行；普通建模不修改注册表。

## 按需读取

- 本地 DirectSession、COM 兼容和命令：读取 [references/local-workflow.md](references/local-workflow.md)。
- COM 连接、进程归属和版本差异：读取 [references/compatibility.md](references/compatibility.md)。
- 其他工程域：读取上游 `solidworks-automation-skill` 中与任务匹配的子技能，不读取无关模块。

## 入口脚本

新建普通零件时，将本技能的 `scripts` 目录加入 `sys.path`，从 `local_sw` 导入 `DirectSession`、建模助手和 `verify_part_delivery()`。输出放入独立任务目录，不覆盖旧成果。具体调用见 `references/local-workflow.md`。
