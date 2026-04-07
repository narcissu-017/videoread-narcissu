# 排版算法说明

本文档说明 VideoRead 当前公开版本里使用的主要平铺算法。

## 设计目标
这套排版逻辑主要服务于多视频同时审阅，重点是：
- 保持视频原始顺序
- 保持显示比例
- 尽量减少明显空白
- 横屏与竖屏混排时尽量提高空间利用率
- 在窗口缩放时仍保持稳定

## 算法 1：稳定分行排版
算法 1 更偏稳定和可预期。它会围绕当前行数做分行计算，但不会把每个视频强行切成完全相同的格子，而是根据每个视频的宽高比给出更合理的分配。

核心过程：
1. 把每个视频抽象成宽高比。
2. 在目标行数附近搜索候选方案。
3. 用动态规划决定每一行放哪些连续视频。
4. 按整体利用率和单图行惩罚来选择布局。

核心片段：
```python
for candidate_rows in range(min_rows, max_rows + 1):
    dp = [[float("inf")] * (count + 1) for _ in range(candidate_rows + 1)]
    prev = [[-1] * (count + 1) for _ in range(candidate_rows + 1)]
    dp[0][0] = 0.0

    for row in range(1, candidate_rows + 1):
        for end in range(1, count + 1):
            for start in range(row - 1, end):
                ratio_sum = prefix_ratio[end] - prefix_ratio[start]
                width_variance = abs(ratio_sum - target_ratio_per_row)
                single_penalty = 0.32 if end - start == 1 and count > candidate_rows else 0.0
                cost = dp[row - 1][start] + width_variance + single_penalty
                if cost < dp[row][end]:
                    dp[row][end] = cost
                    prev[row][end] = start
```

### 适合场景
- 想要更稳定的结果
- 希望窗口缩放时布局风格不要跳动太大
- 仍然把“行数”当作一个参考参数

## 算法 2：Justified 风格排版
算法 2 会搜索一批目标行高，用 justified layout 的思路把视频划分成多行。它更关注整体利用率，也更适合横屏、竖屏混排。

核心公式：
```python
height = total_w / ratio_sum
```

含义是：
- 一行中所有视频按同一行高计算宽度
- 行宽尽量铺满可用宽度
- 根据内容本身比例自然决定每行放多少视频

核心过程：
```python
target_h = min_target_h
while target_h <= max_target_h + 0.1:
    dp = [float("inf")] * (count + 1)
    prev = [-1] * (count + 1)
    row_heights = [0.0] * (count + 1)
    dp[0] = 0.0

    for end in range(1, count + 1):
        start_floor = max(0, end - 8)
        for start in range(start_floor, end):
            ratio_sum = prefix_ratio[end] - prefix_ratio[start]
            height = total_w / ratio_sum
            cost = dp[start]
            cost += ((height - target_h) / max(1.0, target_h)) ** 2
            if end - start == 1 and count > 3:
                cost += 0.45
            if height < 82:
                cost += ((82 - height) / 82) * 2.6
```

最终还会综合考虑空白和过矮行：
```python
total_layout_h = sum(heights_out)
blank_ratio = max(0.0, total_h - total_layout_h) / max(1.0, total_h)
overflow_ratio = max(0.0, total_layout_h - total_h) / max(1.0, total_h)
short_penalty = max(0.0, 110.0 - min_height) / 110.0
total_cost = dp[count] * 0.35 + blank_ratio * 3.8 + overflow_ratio * 2.4 + short_penalty * 1.8
```

### 适合场景
- 更看重整体铺满效果
- 横屏和竖屏视频混排较多
- 想尽量减少右侧和底部空白

## 覆盖条件
无论使用哪种算法，当前实现都遵守这些约束：
- 不改变视频顺序
- 不裁切内容
- 不拉伸变形
- 允许在窗口不足时整体缩小
- 允许在不同窗口大小下重新计算最优分行

## 实际取舍
在“保持顺序 + 保持比例 + 不裁切”的前提下，某些组合不可能做到完全没有空白。
算法的目标不是绝对消灭空白，而是在可读性、稳定性和空间利用率之间取得更自然的平衡。
