# 组合梁配置：已验证接口与故障

本页只适用于assets/composite-beam/spec.json中的两个任务。参考源码来自已跑通且经开发者审查的教学案例，保留可读CAE操作，不是模型从零独立生成的脚本。

## 物理条件

X为长度，Y为厚度，Z为宽度。长640 mm、宽16 mm、两层各26 mm。下钢E=203000 MPa、ν=0.26；上铝E=75000 MPa、ν=0.31。总载荷2000 N，在X=200/440、Y=52的截面各加载1000 N；按二次边节点权重分配。下层左底边U1/U2/U3固定，右底边U2/U3固定、U1自由。

Tie绑定时整体中性轴约Y=20.01 mm。滑移采用Initial步SMALL、SURFACE_TO_SURFACE；法向HARD、DIRECT、允许分离，切向FRICTIONLESS。上层(0,26,0)约束U1/U3，(640,26,0)约束U3。每层512个C3D20R单元、2945节点；小变形静力，无人工稳定化。

测点位于X=320、Z=0；P2—P9为E11，P1/P10为外表面E33。按同一实例的ELEMENT_NODAL贡献算术平均。界面法向为Y，对应应力S22；E33为宽度应变。

## 故障与处理依据

|阶段|观察到的问题|方法中的处理|
|---|---|---|
|教师Region练习|CellArray直接传给SectionAssignment.region|该错误明确人为设置，记录为教师故障演示|
|历史qwen建议|p.Set(cells=p.cells)遗漏name|保存真实失败；开发者补成具名Set，单独记录贡献|
|接触代码|误用Model.contactProperties|依据真实属性错误，提供版本对应的API卡片|
|任务完整性|给出接触代码却漏掉上层定位|执行前复核自由度；开发者修正不记成模型自主完成|
|物理验收|用Tie成功算完滑移任务|独立读INP检出界面与定位不符；文件存在和求解成功均不足|
|评价输出|引用technical_status而非已有证据编号|反馈拒收，保留原始响应，限定编号后修正|

## 经过实际使用的接口卡片

- p.SectionAssignment(region=p.Set(name='SOLID',cells=p.cells),sectionName=key)。不同Part中集合名称可以相同；同一Part中应避免冲突。
- cp=m.ContactProperty('INTER_PROP')返回属性对象，在cp上设置NormalBehavior和TangentialBehavior；不要凭名称猜测Model上有contactProperties。
- SurfaceToSurfaceContactStd使用基线已定义的bottom/top表面。当前Abaqus 2026示例使用main/secondary，不把历史master/slave参数名直接混用。
- 实际INP检查SURFACE INTERACTION、SURFACE BEHAVIOR、CONTACT PAIR和TIE；不采信模型自行描述的关键字。
- 对其他软件版本，先核对该版本官方接口与一个最小实际算例，不根据本案例推定所有版本兼容。

参考应变容差为max(5%参考绝对值,2με)，整体合力/力矩相对残差不超过1%。CSV与独立ODB取值另作严格一致性核对。参考解采用同条件软件设定，证明实现一致性，不等同物理实验真值。

官方参考：[Abaqus scripting interface](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECMDRefMap/simacmd-m-Use-sb.htm)。版本相关细节以上述2026真实执行为依据。
