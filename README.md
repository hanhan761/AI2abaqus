# AI2abaqus

**把AI建议转化为有真实执行与独立核验证据的Abaqus仿真。**

AI2abaqus是一项可安装的agent skill，也是AI辅助仿真教学方法的可执行载体：任务契约 → 力学预判 → 局部AI修改 → 审查执行 → 独立核验 → 提交反馈。研究配置固定使用 **qwen3.7-plus**。当前版本 **0.1.0**。

*An evidence-oriented skill for reviewed AI-assisted Abaqus modeling, execution, verification, and formative assessment.*

## 技术成果包含什么

- **方法入口**：SKILL.md规定状态转换、交互上下文、责任分工与停止条件。
- **可执行工具**：精确源码修改、来源与哈希、审查绑定、隔离运行目录、故障分类、不可静默更改的任务契约。
- **独立核验**：读取实际INP与ODB，核对CSV、独立数值参考和整体平衡，重开CAE并从源码清洁复跑；力学预判另行复核。
- **教学与评价**：六项提示支架、五维量规、证据编号、无效反馈拒收和教师最终复核。
- **首个任务配置**：上铝下钢组合梁四点弯曲的绑定/滑移变式，以及真实历史qwen建议和人工修正的回放材料。

这一成果使论文可以评测具体的方法与工具机制：哪些环节完成、错误在哪被发现、人工介入做了什么、结果能否复现。对照和消融方案写在评测协议中，尚未运行的试验不写成结果。

## 当前验证状态

所有本次代码测试与Abaqus相关验证均在已授权的3090工作站Windows虚拟机执行。

|证据|范围与状态|
|---|---|
|此前真实教学案例|绑定、滑移两个案例完成求解、独立取数、CAE重开与清洁复跑；均包含明确的教师支架和开发者修正|
|本次skill代码|31项单元与不变量测试通过，官方skill格式检查通过；详见evidence/validation.json|
|本次真实ODB组件核查|新验收代码读取此前实际ODB，逐项核对INP、CSV、应变和平衡；不冒充新增求解|
|本次完整重算回放|许可服务当前不可达，在进入CAE建模前报FlexNet连接失败；本轮未完成新的端到端回放|
|真实学生学习效果|尚无数据；模拟提交和开发者回放不作学习增益证据|

首次回放暴露了“把环境失败当成预期代码失败”的问题，已增加故障分类与遇到许可/环境错误立即停止的规则，并设置回归测试。原失败记录保留。历史响应回放的**新增模型请求数为0**。

详细证据与文件来源见 [evidence/validation.json](evidence/validation.json) 和 [数据来源](references/data-provenance.md)。

## 安装与调用

将整个仓库置于Codex技能目录ai2abaqus下，例如Windows PowerShell：

~~~powershell
git clone https://github.com/hanhan761/AI2abaqus.git (Join-Path $env:USERPROFILE '.codex/skills/ai2abaqus')
~~~

新会话中调用：

~~~text
使用 $ai2abaqus，在我授权的虚拟机上完成组合梁绑定与滑移仿真。
先明确力学条件与预判，用qwen3.7-plus辅助局部修改，保存人工审查、真实运行与独立核验证据。
~~~

skill不内置模型服务账户或Abaqus许可证。使用已有授权服务；当前代理不是qwen时，不能把代理自身输出登记成qwen结果。

## 先验证软件环境

控制脚本使用Python 3.10+标准库；ODB提取器由Abaqus Python运行。Windows请指定原生启动器。下例reference模式使用已经审查的完整基线，验证环境和工具链，不是新的AI生成试验。

~~~powershell
$abaqusLauncher = 'C:/Program Files/SIMULIA/EstProducts/2026/win_b64/code/bin/SMALauncher.exe'
& $abaqusLauncher python scripts/ai2abaqus.py init --workspace workspaces/demo --case tied --mode reference --target-id authorized-vm
& $abaqusLauncher python scripts/ai2abaqus.py predict --workspace workspaces/demo --role developer --note '绑定梁刚度加权中性轴约Y=20.01 mm，上压下拉。'
& $abaqusLauncher python scripts/ai2abaqus.py review --workspace workspaces/demo --role developer --note '检查单位、支承、载荷、Tie界面与输出定义。'
& $abaqusLauncher python scripts/ai2abaqus.py run --workspace workspaces/demo --abaqus $abaqusLauncher
& $abaqusLauncher python scripts/ai2abaqus.py verify --workspace workspaces/demo --run-id r0001 --abaqus $abaqusLauncher
~~~

先确认run成功，再选择实际run-id进行verify。工作区绑定初始化时的机器；复制到另一台机器后不能静默运行。许可连接失败属于环境阻断，需恢复授权许可连接后在新目录进行有记录的验证。

## 用AI开展排错与变式

- init的region模式提供明确设置的Region类型练习；interface模式给定Tie基线，目标是滑移任务。
- 先predict，再用status取得当前source_sha256。
- 给qwen提供任务背景、已知条件、修改范围、真实报错、保护条件和交付验收六项上下文，保留原始响应。
- patch JSON包含author_role、model、source_sha256、old、new、explanation，可附receipt_sha256。人工修改使用实际角色，不填model。
- patch只校验哈希、精确替换和Python语法。审查者仍需判断接口与物理条件；独立验收检验实际执行结果。

任何成功结论都保留人工贡献。源码被改动后，旧审查失效；提交文件被改动后，旧反馈证据失效。完整命令、提交格式与量规见[方法契约](references/method.md)、[故障知识](references/beam-failures.md)、[评测协议](references/evaluation.md)。

## 验证与复现

在选定的授权计算机执行单元与不变量测试：

~~~text
python -m unittest discover -s tests -p test_workflow.py -v
~~~

许可证可用时，在新的输出目录进行完整回放：

~~~text
python tests/run_replay.py --output workspaces/replay --abaqus NATIVE_ABAQUS_LAUNCHER --target-id authorized-vm
~~~

该回放包含：教师Region故障、历史模型命名遗漏、开发者修正、接触属性错误、API卡片后的模型代码、开发者定位约束补充，以及两个案例的独立核验、CAE重开和清洁复跑。代码先区分预期脚本故障和环境失败，环境阻断立即停止。回放只重用历史模型文本，仍会实际调用Abaqus，需要许可证。

## 当前边界

内置验收器只覆盖spec.json中的两项线弹性组合梁任务；它不是通用有限元验证器，也不是任意Python代码的安全沙箱。独立数值参考与待验实现采用相同物理设定和软件，不等同实物实验真值。新几何、本构、接触或软件版本需要新的任务契约、参考与实际验证。

## 配套教程 v1.0

[学生教程与教师附录](tutorials/README.md)面向材料力学已学、Abaqus初学的本科生，采用教师预配置skills助手入口，按4学时组织条件分析、绑定排错、滑移变式、结果解释与提交。每单元提供输入示例、自检与阶段产物。

本次为文档与教学资源更新，技能代码仍为v0.1.0；没有新增模型请求、求解或课堂效果数据。教师上课前应核对模型服务、许可和完整流程。
