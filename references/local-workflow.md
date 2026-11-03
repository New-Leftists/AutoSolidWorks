# 本地执行方式

这是可移植的执行约定；不要把用户机器的绝对路径写进 Skill。用 `AUTO_SOLIDWORKS_UPSTREAM` 指向上游 `solidworks-automation` 目录，未设置时使用用户默认的上游 Skill 目录。

普通零件的最小入口：

1. 先运行上游 `scripts/sw_preflight.py`，确认 SolidWorks、Python、`pywin32`/`comtypes` 和注册状态。
2. 将本技能的 `scripts` 目录加入 `sys.path`，从 `local_sw.py` 导入 `DirectSession`、建模助手和 `verify_part_delivery()`。
3. 每个任务创建新的输出目录；保存原生文件后重开、重建、导出并读取审查报告。

`DirectSession` 只登记本轮新建文档。SolidWorks 已有用户文档时，不修改、不关闭它们；不要通过强杀进程解决连接失败。

只有在当前任务需要时，才读取上游对应的零件、孔槽、装配、工程图或高级几何参考。不要把上游完整手册复制到本 Skill，也不要在入口预加载所有模块。

详细的 Python 调用应放在本次任务工作目录的脚本中；Skill 目录只保存可复用的连接和验证逻辑。
