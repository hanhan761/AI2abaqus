---
name: ai2abaqus
description: 用AI协助把力学任务转成可追溯的Abaqus建模、排错、求解与独立核验；组织任务契约、局部代码修改、审查记录和过程性评价。用户要求AI驱动Abaqus、有限元教学案例或相关方法评测时使用。内置验收器目前仅覆盖组合梁线弹性四点弯曲配置。
metadata:
  version: "0.1.0"
---

# AI2abaqus

目标是得到有证据支持的仿真结果，并保留建模判断。交付任务条件、力学预判、模型建议、代码差异、真实运行和独立核验；清楚记录开发者、教师、学生与模型各自的贡献。

## 先确定任务与执行位置

- 沿用用户已授权的计算机与模型服务。用户已经指定机器时，直接使用；缺少执行位置时只澄清必要信息。禁止悄悄转到本机运行。
- 本研究配置使用 qwen3.7-plus。当前代理并非该模型时，通过用户现有服务调用，不把当前代理的输出记为 qwen。保存完整回复与调用凭据的非敏感摘要；不复制账号配置或密钥。
- 当前内置配置是 Abaqus 2026、N/mm/MPa、上铝下钢的线弹性组合梁。它的几何、网格、界面、载荷和容差见 [任务配置](assets/composite-beam/spec.json)。其他问题可以沿用方法，但需要另建并验证专用配置；不能套用组合梁验收器宣布通过。
- 后台子进程不显示控制台。Windows使用原生 SMALauncher.exe，脚本已经设置 CREATE_NO_WINDOW，不使用拼接shell命令。

## 根据工作选择材料

- 开展新仿真、解释和排错：读 [方法与证据契约](references/method.md)。
- 组合梁接口或物理错误：按需读 [已验证接口与故障](references/beam-failures.md)。
- 设计论文评测或教学提交：读 [评测协议](references/evaluation.md)。
- 验证安装与重放案例：执行 tests/run_replay.py。它消费历史真实模型响应，明确标记为回放，不产生新的模型请求。

## 执行工作流

1. 将题目写成任务契约，记录单位、坐标方向、材料、界面、支承、载荷、测点和验收条件。先写力学预判，再查看计算结果。未知条件显式保留，不替用户猜出关键物理设定。
2. 使用可读基线生成局部问题，向 qwen 提供六项上下文：任务背景、已知条件、修改范围、真实报错、受保护条件、交付与验收。保留原始回复；按实际来源标注代码。
3. 将修改写入带源文件哈希、精确旧片段、新代码、解释和来源的patch JSON。使用 patch 命令应用；由实际审查者记录理由与角色。开发者修正标为 developer，不能记成模型或真实学生完成。
4. 记录审查后执行实际软件。程序要求预判存在、任务契约未变、当前源码与审查哈希一致，并在新目录保存每次提交。退出码、文件存在或AI的完成宣告均不单独构成验收。
5. 独立读实际INP与ODB：先查物理设置和数据提取，再查参考/理论、整体平衡；重新打开保存的CAE，并从源码在清洁目录再算。完整通过后才报告本任务验收通过。失败时定位最先阻断的环节，保留失败版本，不覆盖记录。
6. 收集过程文件并生成证据编号。AI仅提供五维建议、理由和补交行动；feedback命令检查分值和引用，拒收记录保留。教师最终评分保持待复核。

## 工具入口

在用户授权的计算机执行，工作目录位于本skill根目录。Python 3.10+，普通控制脚本仅用标准库；读取ODB需要Abaqus的Python。

~~~text
python scripts/ai2abaqus.py init --workspace workspaces/demo --case tied --mode region --target-id authorized-vm
python scripts/ai2abaqus.py predict --workspace workspaces/demo --role developer --note "根据刚度加权，绑定梁中性轴约Y=20.01 mm，上压下拉。"
python scripts/ai2abaqus.py status --workspace workspaces/demo
python scripts/ai2abaqus.py patch --workspace workspaces/demo --input incoming_patch.json
python scripts/ai2abaqus.py review --workspace workspaces/demo --role developer --note "说明实际检查的范围、接口和力学条件"
python scripts/ai2abaqus.py run --workspace workspaces/demo --abaqus NATIVE_ABAQUS_LAUNCHER
python scripts/ai2abaqus.py verify --workspace workspaces/demo --run-id r0001 --abaqus NATIVE_ABAQUS_LAUNCHER
~~~

示例中的占位路径需要替换为该授权机器的真实启动器；软件失败后应选择实际成功的run-id，不能固定选r0001。reference模式直接使用已审查示例，用于环境验证；region和interface模式分别用于对象类型故障与界面变式。

模型patch字段：model固定为qwen3.7-plus，author_role为model，source_sha256为status给出的当前哈希，old/new为精确字符串，explanation说明理由。可附receipt_sha256关联原始响应。人工修正用实际author_role（developer/teacher/student），不填model。哈希关联不能证明模型身份，需保留真实调用记录。

source改变后旧审查失效；任务条件改变则新建会话。未知调用终态不自动重试，不静默扩大请求或求解预算。普通局部问题先用有限完整回复诊断，有新日志再继续修正；超出既定范围时明确记录剩余问题与所需介入。

## 完成与报告

报告当前阶段、软件运行结果、独立验收、人工介入、失败原因与证据位置。将模型调用次数、软件提交次数、清洁复跑分别计数。既有示例通过只支持该配置的实施；回放不等于新模型试验，模拟提交不等于真实学生学习效果。过程量规与反馈格式见评测协议。
