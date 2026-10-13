---
id: laft-kessler-fortran
title: Fortran 物理过程上 GPU：LAFT 让四个大模型翻成 Kessler 暖雨方案
title_en: LAFT ports Kessler warm-rain physics across four Fortran models
summary: 自动代码翻译在软件工程里转了几十年。从 TXL 这类规则变换系统，到基于静态分析、中间表示和领域专用规则的方案。它们对翻译行为的控制得极死，代价是要为每个源语言—目标语言组合手写变换逻辑。
category: 论文
tags: [Fortran, GPU, 模式物理]
published: 2026-10-11
author: AetherWatch Desk
source: AetherWatch Observation
lang: zh
---

自动代码翻译在软件工程里转了几十年。从 TXL 这类规则变换系统，到基于静态分析、中间表示和领域专用规则的方案。它们对翻译行为的控制得极死，代价是要为每个源语言—目标语言组合手写变换逻辑。大模型填了这个思路：能吃更宽的上下文，写出的目标语言更像人写的。已有研究也证明，在提示中给足上下文能改善翻译质量。

天气模式是这一技术最不浪漫、最有用的试验场。Kessler 暖雨方案只有几百行 Fortran，却被 GFS、GRAPES 类区域模式、研究用 LES 和理想化暖泡试验反复复制。每一个副本都有自己的数组布局、OpenMP 指令和 saturation adjustment 顺序。

## 四个模型，一个方案

LAFT 的做法不是“把整个模式扔进上下文窗口”，而是：

1. 先用静态分析切出物理过程的纯函数内核；
2. 把内核连同数组内存布局说明一起交给模型；
3. 用一套 Kessler 单元试验当验收器——水成物守恒、饱和调整单调性、零降水的干气柱。

最快的可运行版本，比手写移植大约少了两个数量级的人时，也仍然需要人把 GPU 的 shared memory 和 Fortran `do concurrent` 对上。AetherWatch 记录这件事，是因为它改变的不是技巧评分，而是**一个物理方案从论文到业务的时间常数**。
