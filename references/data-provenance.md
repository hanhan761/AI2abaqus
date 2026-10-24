# 数据来源与用途

- assets/composite-beam/reference中的JSON来自此前独立参考计算，与待验实现使用同一物理条件和Abaqus版本；不是实物测量。源文件哈希保存在provenance中。
- tests/fixtures中的INP、CSV和extracted.json来自此前实际教学实现，用作已知输入、错误任务、篡改数据等组件回归测试；它们没有被当作独立参考解。INP注释已删除，保留计算关键字与数据。
- assets/composite-beam/replays保留历史真实qwen响应的代码、解释与原始收据SHA-256。开发者修正单独标注；回放控制器为当前源码重新绑定old片段与source_sha256，这些控制器操作不冒充模型原始回复。
- evidence中区分此前完整教学案例验证、本次skill单元验证、当前真实ODB组件核验与本次许可环境阻断。没有真实学生数据。

组合梁配置的适用范围有限。参考一致性、理论趋势和平衡共同支持实现校核，不能将同软件数值参考的一致性误称为实验精度。
