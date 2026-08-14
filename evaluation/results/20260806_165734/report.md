# 活动策划系统质量评估报告

用例数: 12  |  成功: 12

## 客观指标

| 指标 | 值 |
|---|---|
| 需求提取准确率 | 0.78 |
| 方案约束召回率 | 0.92 |
| 方案约束准确率 | 0.979 |
| 工具真实命中率 | 1.0 |
| 结构完整性 | 1.0 |

## 质量维度分（5 分制）

| 维度 | 均分 |
|---|---|
| 完整性 | 5.0 |
| 可执行性 | 5.0 |
| 预算合规 | 4.08 |
| 逻辑一致 | 4.75 |
| 信息真实 | 4.83 |

## 用例明细

### case_01: 帮我策划一个500人的公司年会，预算20万，地点在北京朝阳，时间是下个月中旬
- success: True
- 提取: {'correct': 5, 'checked': 5}
- 约束: {'total': 5, 'covered': 5, 'correct': 5}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_02: 策划一个200人的产品发布会，预算50万，上海浦东，需要高端场地
- success: True
- 提取: {'correct': 5, 'checked': 5}
- 约束: {'total': 5, 'covered': 5, 'correct': 5}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_03: 组织一场100人的客户答谢会，预算10万，广州天河，注重用户体验
- success: True
- 提取: {'correct': 5, 'checked': 5}
- 约束: {'total': 5, 'covered': 4, 'correct': 4}  (recall=0.8, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_04: 安排一个300人的培训会，预算15万，深圳南山，需要完善的设备
- success: True
- 提取: {'correct': 5, 'checked': 5}
- 约束: {'total': 5, 'covered': 5, 'correct': 5}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 4, '信息真实': 5}

### case_05: 帮我策划一个活动
- success: True
- 提取: {'correct': 0, 'checked': 0}
- 约束: {'total': 0, 'covered': 0, 'correct': 0}  (recall=None, precision=None)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_06: 策划一个户外产品发布会，需要无人机表演和现场直播
- success: True
- 提取: {'correct': 1, 'checked': 2}
- 约束: {'total': 2, 'covered': 2, 'correct': 2}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 1, '逻辑一致': 3, '信息真实': 4}

### case_07: 办一个20人的高端私密商务晚宴，预算3万，上海黄浦区
- success: True
- 提取: {'correct': 5, 'checked': 5}
- 约束: {'total': 5, 'covered': 4, 'correct': 4}  (recall=0.8, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 2, '逻辑一致': 5, '信息真实': 5}

### case_08: 组织一场2000人的企业运动会开幕式，预算100万，北京
- success: True
- 提取: {'correct': 4, 'checked': 4}
- 约束: {'total': 4, 'covered': 4, 'correct': 4}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_09: 办一个300人的技术峰会，预算只有5万，成都，尽量控制成本
- success: True
- 提取: {'correct': 0, 'checked': 4}
- 约束: {'total': 4, 'covered': 4, 'correct': 4}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 4}
- errors: ['需求提取 JSON 解析失败: Expecting value: line 1 column 1 (char 0)']

### case_10: 下周五就要办一场200人的团队建设活动，预算8万，时间很紧
- success: True
- 提取: {'correct': 3, 'checked': 4}
- 约束: {'total': 4, 'covered': 3, 'correct': 2}  (recall=0.5, precision=0.667)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_11: 策划一场圣诞节主题的客户答谢会，150人，预算12万，深圳福田区
- success: True
- 提取: {'correct': 6, 'checked': 6}
- 约束: {'total': 6, 'covered': 6, 'correct': 6}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 5, '逻辑一致': 5, '信息真实': 5}

### case_12: 办一场科技感十足的400人公司年会，需要AR互动和机器人主持，预算30万，杭州
- success: True
- 提取: {'correct': 0, 'checked': 5}
- 约束: {'total': 5, 'covered': 5, 'correct': 5}  (recall=1.0, precision=1.0)
- 工具命中: {'场地': True, '商家': True, '流程': True}
- 结构: {'概述': True, '流程': True, '场地': True, '商家': True, '预算': True, '任务': True, '风险': True}
- 质量分: {'完整性': 5, '可执行性': 5, '预算合规': 1, '逻辑一致': 5, '信息真实': 5}
- errors: ['需求提取 JSON 解析失败: Unterminated string starting at: line 10 column 38 (char 223)']
