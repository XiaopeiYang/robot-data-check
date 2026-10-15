# 代码导读（给自己读懂、讲清楚用）

按下面的顺序读。每个文件记住一个核心设计决定，并能回答对应的练习题。

## 1. `engine/results.py`：契约
- `RESULTS_SCHEMA` 是所有下游（报告、viewer、以后的 pipeline、MCP）唯一依赖的东西
- 检查只返回 `Issue`；`dataset`、`revision`、`shard`、检查名和版本都由 runner 统一填。这样检查不可能写错契约
- `frame_start` / `frame_end` 是闭区间，按 `frame_index` 计；问题针对整集时为 NULL
- **练习**：如果要加一列 `confidence`，需要改哪几处？旧的 `results.parquet` 怎么办？（提示：看 `cli/main.py` 里 `view` 怎么补齐缺失的列）

## 2. `engine/registry.py` + `checks/__init__.py`：检查的接口
- 一个检查就是 `NAME`、`VERSION` 加一个 `run(con, ctx) -> list[Issue]`，没有基类、没有注册魔法
- `VERSION` 是给增量处理用的：检查逻辑变了，旧结果就失效
- **练习**：为什么不让检查直接写文件？

## 3. `engine/loader.py`：只下载需要的部分
- Hub 数据集先固定到 commit sha，结果才可复现，也为 Phase 2 的增量判断打好基础
- `meta/episodes` 按顺序取，一旦覆盖到所需范围就停；数据文件只下载所选 episode 所在的那几个
- 本地目录和 Hub 走同一套逻辑，只有 `fetch` 不同。测试就靠这一点，完全离线
- **练习**：为了支持 v2.1，loader 要改什么？（v2.1 是每集一个数据文件，元数据在 jsonl 里）

## 4. `engine/views.py`：一切检查都是对视图写 SQL
- 三个视图：`frames`、`episodes`、`tasks`，都已经按 episode 范围过滤好了
- 列名里有 `.` 或 `/` 的要加双引号：`"observation.state"`、`"stats/action/mean"`
- `tasks.parquet` 的任务文本可能在 `__index_level_0__` 列里（pandas 写入时留下的）
- **练习**：为什么用 VIEW 而不是把数据 COPY 进表？

## 5. `checks/frame_index.py`：检查的写法模板
- 用 `LAG` 比较相邻帧，一条 SQL 用 `UNION ALL` 把三种问题合在一起
- 缺帧每个缺口报一条（定位精确），重复帧每集报一条（只给范围）
- **练习**：一集的前两帧都丢了，会报几条、每条是什么？自己推一遍，再用 `delete_frames` 验证

## 6. `tests/`：合成数据 + 故障注入
- `synthetic.py` 用 DuckDB 生成一个干净的 v3 数据集，结构和 DROID 一致，带一路假相机
- `faults.py` 用 SQL 改写数据文件；故意不改元数据，模拟真实的录制 bug
- 每个检查都要有两类测试：干净数据零误报、注入一个故障恰好查出这一个
- **练习**：给 `timestamps` 写一个 `drop_frames_keep_indices` 注入函数，思路是什么？

## 7. `cli/main.py` + `cli/report.py`
- `check` 命令：加载 → 建视图 → 跑 `ALL_CHECKS` → 写 parquet 和 `summary.md`
- 报告只读结果表，所以 pipeline 产生的结果也能用同一套报告

## 8. `viewer/server.py`：只是 engine 外面的一层薄适配
- 复用 `load_dataset` 和 `connect`；结果复制成一张真正的表，因为每个请求都用 `con.cursor()`，看不到 register 的 Arrow 视图
- 视频不经过服务器：返回 Hub 的 URL，浏览器直接用 range 请求去读；本地数据集才由 `/videos` 提供，并防止路径穿越
- **练习**：为什么视频不走后端代理？如果 Hub 不支持 range 请求会怎样？

## 9. `viewer/static/app.js`：时钟
- 第一路视频是主时钟，其他视频偏差超过 0.1 秒就校正；没有视频时用计时器驱动
- 一个视频文件里首尾相连地装着很多集，所以播到本集结尾必须主动暂停
- 曲线的横轴是 `frame_index / fps`，不是录制的 `timestamp`：坏时间戳正是要检查的东西，不能让它扭曲曲线
- 所有数据集文本都用 `textContent` 插入，防止 XSS

## 10. 检查的开发流程和变异测试
- 流程（详见 `.claude/skills/check-workflow/SKILL.md`）：
  1. 你写 `docs/specs/<check>.md`
  2. 测试 agent 只看 spec，先写测试（此时检查还是桩，测试必须先失败）
  3. 实现 agent 写代码，测试对它只读，用哈希校验
  4. 有分歧由你裁决，记进 spec 的 Decisions
  5. 跑变异测试
  6. 出阅读指南和讲回来的题
- `tools/mutate_sql.py`：每次只改 SQL 的一处（`<` 改成 `<=`、`AND` 改成 `OR`、去掉 `+ 1`、`min` 和 `max` 互换、删掉一个 WHERE 条件……），然后重跑这个检查的测试。改了测试还是通过，就说明测试有漏洞
- 为什么不用 mutmut：检查逻辑都在 SQL 字符串里，mutmut 只改 Python 运算符，碰不到 SQL
- 第一次运行的结果：`frame_index` 杀死 14/16，存活的 2 个都是重复帧范围的 `min` 和 `max` 互换。原因是测试只重复了一帧，起止相同。这是一个真实的测试缺口
- **练习**：为什么一个变异体"让 SQL 报错"不算测试强？工具是怎么区分这种情况的？

## 11. `engine/video.py`、调研脚本和浏览器测试
- `video.py`：按 `episodes` 视图里的 from/to 时间戳解码一集的画面，产出 `(frame_index, 灰度图)`
  - PyAV 自带的 FFmpeg 不支持 HTTPS，所以 Hub 上的视频由 Python 里的 `RangeFile` 用 HTTP range 请求去读，带块缓存
  - PyAV 会关闭传给它的文件对象，所以复用同一个 `RangeFile` 时要套一层 `_KeepOpen`，并先把读取位置归零
- `tools/research/`：Hub 普查和冻结帧调研。都分成 `collect`（联网采集，结果存进 `docs/research/`）和 `report`（只读已提交的数据）两步，文档里的数字都能离线复现
- `tests/e2e/`：浏览器端到端测试，默认跳过；设置 `ROBOCHECK_E2E=1` 才运行，准备方法见 `docs/dev-setup.md`
- **练习**：冻结帧调研为什么用"逐像素完全相同"作为信号，而不是"差异小于某个阈值"？（提示：DROID 外部相机的数据）

## 面试最可能被追问的 5 个问题
1. 为什么用 DuckDB，而不是 pandas 或 Spark？（第 3、4 节；README 的 Design decisions）
2. 怎么证明你的检查是对的？（第 6 节：故障注入、检出率和误报率）
3. 为什么 DROID 上时间类检查查不出东西，你怎么处理的？（`docs/findings/droid_1.0.1.md`）
4. 怎么做到增量和幂等？（第 1、2、3 节：commit sha、`VERSION`、按 shard 写结果）
5. 你怎么判断一个异常是 bug 还是按设计？举个例子。（`verify-finding` skill，空任务那条）
