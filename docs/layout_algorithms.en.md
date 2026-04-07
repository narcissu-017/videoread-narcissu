# Layout Algorithm Notes

This document describes the main tiling algorithms used in the current public release of VideoRead.

## Design Goals
These layout strategies are built for reviewing many videos at once.
The main priorities are:
- preserve the original order of videos
- preserve the display aspect ratio
- reduce obvious empty space
- improve space utilization when horizontal and vertical videos are mixed
- remain stable while the window is being resized

## Algorithm 1: Stable Row Partitioning
Algorithm 1 is more conservative and predictable.
It works around the current row count, but it does not force every video into identical cells.
Instead, it uses aspect ratios to decide how videos should be distributed across rows.

Core process:
1. Convert each video into an aspect ratio.
2. Search several candidate layouts around the target row count.
3. Use dynamic programming to decide which consecutive videos belong to each row.
4. Choose the result based on overall utilization and penalties for single-item rows.

Core snippet:
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

### Best Use Cases
- You want more stable and predictable results.
- You do not want the layout to jump too much while resizing windows.
- You still want the row count to remain a meaningful reference.

## Algorithm 2: Justified-Style Layout
Algorithm 2 searches a range of target row heights and uses a justified-layout idea to partition videos into rows.
It focuses more on overall space utilization and works especially well for mixed horizontal and vertical videos.

Core formula:
```python
height = total_w / ratio_sum
```

Meaning:
- all videos in the same row use the same row height
- the row width is pushed as close as possible to the available width
- the content ratios naturally decide how many videos fit into a row

Core process:
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

The final evaluation also considers empty space and overly short rows:
```python
total_layout_h = sum(heights_out)
blank_ratio = max(0.0, total_h - total_layout_h) / max(1.0, total_h)
overflow_ratio = max(0.0, total_layout_h - total_h) / max(1.0, total_h)
short_penalty = max(0.0, 110.0 - min_height) / 110.0
total_cost = dp[count] * 0.35 + blank_ratio * 3.8 + overflow_ratio * 2.4 + short_penalty * 1.8
```

### Best Use Cases
- You care more about overall filling efficiency.
- You often mix horizontal and vertical videos.
- You want to reduce empty space on the right side and at the bottom as much as possible.

## Shared Constraints
Regardless of which algorithm is selected, the current implementation keeps these constraints:
- video order is preserved
- content is not cropped
- aspect ratio is not distorted
- the layout can shrink when the window becomes smaller
- the layout can be recalculated when the window size changes

## Practical Trade-Offs
Under the constraints of preserving order, preserving aspect ratio, and avoiding cropping, some combinations will always leave a certain amount of empty space.
The purpose of the algorithms is not to eliminate all blank areas, but to balance readability, stability, and space utilization in a more natural way.
