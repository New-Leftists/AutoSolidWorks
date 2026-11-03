# COM 兼容要点

- 优先使用 `AUTO_SOLIDWORKS_PROGID`；未设置时让连接器发现已注册的 SolidWorks 版本。
- 连接前后比较 SolidWorks PID，区分本轮新建实例和用户已有实例。
- `GetActiveObject` 或 ROT 附着失败不等于 SolidWorks 损坏；记录 HRESULT、PID 和桌面执行上下文，再按连接器的单次重试策略处理。
- 不连续启动多个实例，不强杀未知进程，不开放端口或配置远程 DCOM。
- 短线段草图可临时使用 `SketchManager.AddToDB=True`，并在 `finally` 中恢复。
- COM setter 成功不等于结果正确；保存重开后必须回读尺寸、颜色、特征和导出文件。
- 版本不在已验证范围内时保留 `review_required`，不要把一次成功运行扩大为通用兼容承诺。
