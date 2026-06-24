# L1 Refactor — Resume Notes (paused 2026-06-24 ~09:20)

> 用户中途请求暂停 6 小时（cron `64a5e5d7` 预定 2026-06-24 15:17 触发，session-only 可能丢；本文件是双保险）。回来后按本文件继续即可。
> 分支：`feat/l1-knowledge-graph`（已 14 commits 在 `main` 前面）
> 状态：**Plan 4 Task 4 in_progress**（e2e 精度门禁还没过）

---

## 回顾：14 commits 已就绪

```
5e015b1  feat(mybatis): new codemap-mybatis plugin (indexer + link bridge)
fee6844  feat(java): extract annotations + emit Spring http_route metadata
81821d2  feat(java): JavaCallResolverBridge — cross-file FQN call/extends/implements
48b965a  feat(java): emit imports / supertypes / pending_calls for FQN resolver
92fee78  docs(adr): ADR-0013 — Java engine standardizes on tree-sitter, drops scip-java
5c7072f  spike(plan-0): HelloSpring fixture + partial findings (sections 0/3/4)
6b0c3c9  feat(cli): wire project indexers, git hotspots, and emitters into orchestrator
2ce6a2b  feat(core): add language-neutral git change-hotspot analyzer
ac42788  feat(emitters): add Emitter protocol and EmitterRegistry
7ddb68a  feat(indexers): add project-level indexer protocol and registry
a5d284c  feat(core): add table SymbolKind and overrides/accesses_table EdgeKinds
d317e8b  feat(vue): capture axios / fetch http_calls in script blocks
<commit-pending>  feat(aimemory): new codemap-aimemory plugin
```

实际 commit 顺序还含 Plan 4 Task 2/3 一起的那一次。`git log --oneline main..HEAD` 是事实源。

---

## 当前阻塞

`tests/e2e/test_golden_precision.py`（**未 commit**, untracked）3 测试有 2 个 fail。

跑：
```bash
cd /Users/xueqiang/Git/codemap
.venv/bin/python -m pytest tests/e2e/test_golden_precision.py -v --no-cov
```

**根因**：`_edge_signature` / `_simple_name` 字符串解析 SymbolID 提取 simple name 的逻辑不对。Symbol IDs 三类形态：

- Java method: `scip-java . . . src/.../OrderService.java/OrderService#calculateOrderPrice().`
  → simple name 期望 `calculateOrderPrice`
- Route (codemap synthetic): ``scip-route . . . api/POST#`/api/order/price`.``
  → path 期望 `/api/order/price`
- MyBatis sql_mapping: `scip-mybatis . . . src/.../CouponMapper.xml/com.example.hellospring.mapper.CouponMapper#selectByUser.`
  → simple name 期望 `selectByUser`
- Table: `scip-table . . . sf_coupon#` → simple name 期望 `sf_coupon`

**最简单的修法**：把 `_edge_signature` 改成直接用 `codemap.core.symbol.SymbolID.parse(s)` → `descriptors[-1].name`，route 特殊判断（`sid.scheme == "scip-route"` 时从 descriptors 倒数第二/路径段取 path）。

EXPECTED_EDGES 6 条已写好，无需修改：

```python
EXPECTED_EDGES = {
    ("calcPrice", "/api/order/price", "routes_to"),
    ("calcPrice", "calculateOrderPrice", "calls"),
    ("calculateOrderPrice", "selectByUser", "calls"),
    ("selectByUser", "selectByUser", "maps_to"),
    ("selectByUser", "sf_coupon", "accesses_table"),
    ("calcPrice", "/api/order/price", "calls"),  # Vue calcPrice → route
}
```

修完跑全门禁：

```bash
.venv/bin/python -m pytest                                  # 期望 294 + e2e 通过
cd plugins/codemap-java && .venv/bin/python -m pytest --no-cov && cd -
cd plugins/codemap-mybatis && .venv/bin/python -m pytest --no-cov && cd -
cd plugins/codemap-vue && .venv/bin/python -m pytest --no-cov && cd -
cd plugins/codemap-aimemory && .venv/bin/python -m pytest --no-cov && cd -
.venv/bin/ruff check src tests plugins
.venv/bin/mypy src/codemap
.venv/bin/lint-imports --config pyproject.toml
```

全绿后 commit：

```bash
git add tests/e2e/test_golden_precision.py tests/fixtures/scip-samples/HelloSpring/web/OrderList.vue
git commit -m "test(e2e): golden full-stack fixture + precision gate"
```

然后调用 superpowers:finishing-a-development-branch 收尾分支。

---

## 关键约束（用户多次强调）

- **codemap 实际运行不依赖任何外部工具**。所有 plugin 走 entry-point；codemap-core 只依赖 typer/pydantic/rich/pyyaml；codemap-java 多 tree-sitter；codemap-mybatis 只 stdlib；codemap-aimemory 多 pyyaml + 可选 anthropic。开发期可装任何工具，但 `pip install codemap-core` 必须开箱可用。
- 全程 TDD（先写失败测试 → 确认 fail → 写实现 → pass → commit）。
- commit 署名两条 Co-Authored-By（Claude 在前、用户在后，本机 git user.email = qiang_xue0@outlook.com）。

---

## 已建好的能力（用于 sanity check）

在 fixture 上跑一遍 codemap index 确认链路依旧完好：

```bash
cd /Users/xueqiang/Git/codemap/tests/fixtures/scip-samples/HelloSpring
rm -rf .codemap .ai-memory
/Users/xueqiang/Git/codemap/.venv/bin/codemap index --rebuild .
cat .codemap/edges.json | python3 -m json.tool | head -40
```

期望（已实测）：5 edges，覆盖 controller→route, controller→service, service→mapper, mapper→sql_mapping, sql_mapping→table；外加 OrderList.vue 的 `this.$axios.post('/api/order/price', ...)` 经 http_route bridge 命中 route，形成第 6 条边（calls → route）。

---

## 关联文档

- `docs/adr/0013-java-engine-tree-sitter-over-scip-java.md` — 方向决定（弃 scip-java）
- `docs/spikes/2026-06-23-scip-java-findings.md` — Plan 0 勘察记录
- `docs/spikes/2026-06-24-codemap-refactor-execution-readiness.md` — 跨环境交接
- `/Volumes/External HD/Obsidian/Notes/07-Ideas/CodeMap/重构(适配知识图谱)/` — 原 plan 文档（仅供参考；Plan 2/3/4 已按 tree-sitter 路径重写实现）
