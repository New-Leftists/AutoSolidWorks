# Auto SolidWorks Lite

一个面向 Codex skill 工作流的轻量 SolidWorks 自动化技能：根据文字或图片需求创建可编辑模型，并在交付前执行保存重开、参数可编辑性、STEP/STL 导出和结果复核。

## 能力范围

- 普通零件的参数化建模辅助与旋转截面创建。
- 跟踪本轮创建的文档，避免误改或关闭用户原有文档。
- 保存重开、重建、草图检查、尺寸试改与恢复、STEP/STL 导出。
- 输出包含检查结果和文件摘要的 JSON 审查报告。
- 对未覆盖或未经验证的结果保留 `review_required` 状态。

## 目录结构

```text
.
|-- SKILL.md
|-- agents/openai.yaml
|-- references/
|   |-- compatibility.md
|   `-- local-workflow.md
`-- scripts/local_sw.py
```

## 上游依赖

此项目不会复制或再发布上游实现代码。`scripts/local_sw.py` 依赖 [solidworks-automation-skill](https://github.com/wzyn20051216/solidworks-automation-skill) 仓库中的 `scripts` 模块。上游仓库采用 MIT License；请按其仓库中的许可证和声明使用上游文件。

将上游仓库放到默认的依赖查找路径，并安装其依赖（如果已经安装，可复用已有目录）：

```powershell
git clone https://github.com/wzyn20051216/solidworks-automation-skill.git "$HOME/.codex/skills/solidworks-automation"
python -m pip install -r "$HOME/.codex/skills/solidworks-automation/requirements.txt"
```

如果放在其他位置，并且当前目录下有 `solidworks-automation-skill` 子目录，可这样指定依赖目录：

```powershell
$env:AUTO_SOLIDWORKS_UPSTREAM = (Resolve-Path '.\solidworks-automation-skill').Path
```

将本仓库目录命名为 `auto-solidworks-lite`，放入客户端可发现的 skills 目录，例如 `~/.codex/skills/auto-solidworks-lite`。安装后可通过 `$auto-solidworks-lite` 显式调用。本项目与上游依赖应分别保存在两个目录中。

调用示例：

> 使用 $auto-solidworks-lite，创建一个外径 28 mm、内径 20 mm、高 25 mm 的环形零件，保存原生模型，导出 STEP/STL 并复核结果。

## 命令行入口

连接探测：

```powershell
python scripts/local_sw.py --probe
```

创建测试零件并运行交付检查：

```powershell
python scripts/local_sw.py --self-test --output .\work\self-test
```

`--probe` 会连接或启动实例，并读取连接与文档状态，不编辑或关闭用户原有文档。`--self-test` 会创建新的模型并在指定目录写入输出，要求该输出目录尚不存在。命令行检查结果以 JSON 输出到标准输出；多视图与审查文件保存在任务输出目录。

详细调用约定见 [本地执行方式](references/local-workflow.md)，连接和兼容性处理见 [COM 兼容要点](references/compatibility.md)。已有用户文件的修改任务应先另存副本，再在副本上处理。

## 验证范围

仓库附带的 GitHub Actions 仅执行 Python 语法与 skill 元数据检查，不运行真实 CAD 建模。`--self-test` 是手动建模检查入口，不代表全部模型或版本已经通过验证。交付报告中的 `review_required` 项需要继续复核。

## 许可证

本仓库内容依据 [MIT License](LICENSE) 发布。上游依赖有独立许可证；上游代码没有包含在本仓库中。SolidWorks、Codex 及其他第三方产品仍受其各自条款约束。

## 贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。提交前运行静态语法检查，并确认没有加入密钥、用户数据、生成的 CAD 文件或本机路径。
