# CodeMap 知识图谱重构 —— 执行就绪评估与环境交接

> 创建时间：2026-06-24
> 作者：Claude（按用户「读重构文档→按顺序实现」请求，在动手前做的批判性审查 + 环境勘察）
> 状态：**未动手实现**。本机缺 scip-java 工具链，用户决定换环境继续。本文是交接清单。
> 关联计划文档（在 Obsidian vault）：
> `07-Ideas/CodeMap/重构(适配知识图谱)/` 下的
> `…-design.md` / `plan-0-验证spike` / `plan-1-地基` / `plan-2-java语义核心` /
> `plan-3-框架bridge` / `plan-4-贯通与输出`
> 现有代码库：`/Users/xueqiang/Git/codemap`（git，随仓库可带到新环境）

---

## 0. 一句话结论

5 个 plan 质量很高、可逐步 TDD 执行；**Plan 1（地基）完全不依赖 scip-java，现在/任何环境都能立即开工**。但**文档字面顺序的第一步 Plan 0（验证 spike）被本机工具链阻塞**：`scip-java / maven / gradle / coursier / protoc` 全缺。Plan 2/3/4 中凡是需要**真实 `index.scip`** 的部分都连带阻塞。建议在新环境先装工具链跑 Plan 0，或先在任意环境把 Plan 1 + 不依赖真实 `.scip` 的部分做掉。

---

## 1. 本机环境勘察（2026-06-24，xueqiang的MacBook Pro）

| 工具 | 状态 | 说明 |
|---|---|---|
| Java | ✅ `17.0.17 LTS` (`/usr/bin/java`) | 满足目标 JDK 17 |
| Python | ✅ `3.14.5` | 满足 `requires-python >=3.11` |
| scip-java | ❌ 未安装 | **Plan 0/2 的硬前置** |
| maven (`mvn`) | ❌ 未安装 | scip-java 索引需要可构建的 mvn/gradle |
| gradle | ❌ 未安装 | 同上（二选一） |
| coursier (`cs`) | ❌ 未安装 | scip-java 官方推荐安装途径 |
| protoc | ❌ 未安装 | Plan 2 生成 `scip_pb2.py` 需要（或用 `pip install grpcio-tools` 自带 protoc） |

**新环境上手前需补齐**：scip-java、maven（或 gradle）、protoc（或 grpcio-tools）。另需一个**可 `mvn compile` 通过的目标 Java 工程**（Plan 0 Task 3 / Plan 4 golden fixture 的真相源）。

新环境建议安装命令（macOS / Homebrew，供参考，未在本机执行）：

```bash
brew install coursier/formulas/coursier && cs setup     # 装 JVM 工具基座
cs install scip-java                                     # 装 scip-java
brew install maven                                       # 或 gradle
pip install grpcio-tools                                 # 自带 protoc，给 Plan 2 生成 scip_pb2.py
scip-java --help                                         # 验证可用
```

---

## 2. 计划审查：硬编码 API vs 真实代码（已逐项核对）

对 Plan 1（直接硬编码了大量 codemap 内部 API）做了逐项核对，结论：**Plan 1 可按文档原样执行**。核对覆盖到 Plan 2–4 用到的跨层 API。

### 2.1 与计划假设一致（可放心按文档写）

- `src/codemap/core/models.py`
  - `SymbolKind` Literal 现含 `… "asset", "unknown"`；`EdgeKind` Literal 现含 `… "maps_to", "imports"`。Plan 1 Task 1 要加 `"table"`（SymbolKind）、`"overrides"`/`"accesses_table"`（EdgeKind）——位置假设成立。
  - `Confidence = Literal["high","medium","low"]`（注意：核心 Confidence **不含** `"llm"`；`"llm"` 只出现在 enrichment YAML，物理隔离，符合设计）。
  - `Symbol`/`Edge`/`Range`/`Annotation`/`Diagnostic`/`IndexResult` 字段与计划用法一致；`Symbol.extra: dict[str, Any]`、`Symbol.annotations: list[Annotation]` 存在。
- `src/codemap/core/symbol.py`
  - `SymbolID.parse(s) -> SymbolID`（classmethod）✅；`to_string()` + `__str__` ✅；构造参数 `scheme`（必填）、`manager="."`、`package_name="."`、`package_version="."`、`descriptors: tuple[Descriptor,...]=()`（`@dataclass(frozen, slots)`）。
  - `SymbolParseError(ValueError)` ✅。
  - `Descriptor(name, kind, disambiguator="")` ✅；`DescriptorKind`(StrEnum) 成员 `NAMESPACE/TYPE/TERM/METHOD/TYPE_PARAMETER/PARAMETER/META` ✅（Plan 用到的 TYPE/METHOD/TERM/NAMESPACE 全在）。
  - `SymbolID.descriptors` 元素有 `.name`/`.kind` ✅。
- `src/codemap/core/store.py`
  - `ReadOnlyStore` 是 `@runtime_checkable Protocol`，方法 `get / iter_symbols / iter_edges / callers / callees / search / manifest`。emitter（Plan 1 Task 3 / Plan 4）只用 `iter_symbols`/`iter_edges`，满足。
  - 另有 `SymbolStore(ReadOnlyStore, Protocol)` 读写协议。
- `src/codemap/io/json_store.py`
  - `JsonStore.open(root, *, mode="rw")`（classmethod，返回支持 `with` 的实例）✅；`iter_symbols/iter_edges/upsert_symbols/upsert_edges/upsert_routes/upsert_diagnostics/commit/get` 全部存在，签名与 Plan 用法一致；额外有 `upsert_aliases/iter_routes/iter_aliases/iter_diagnostics/delete_by_file/clear_bridge_outputs`。结构上满足 `ReadOnlyStore`/`SymbolStore`。
- `src/codemap/indexers/base.py` + `registry.py`
  - `Indexer` Protocol：`index_file(path, source: bytes, ctx) -> IndexResult`；`supports(path)`；ClassVar `name/version/file_patterns/languages`。
  - `IndexContext(project_root: Path, relative_path: PurePosixPath, language: str, config={})`（**`relative_path` 是 `PurePosixPath` 不是 str**）。
  - entry-point group `codemap.indexers`，发现机制 `entry_points(group=…)→ep.load()()→isinstance 校验→按 name 入表`。Plan 1 的 project_indexers / emitters 注册表照抄此模式即可。
- `src/codemap/cli/commands/index.py`
  - `_run_bridges(store, stats, config)` ✅、`_index_one(file_path, project_root, store, registry, stats, bar, config)` ✅、`_do_incremental(...)` ✅、`_index_one_prefetched(...)` ✅。
  - **full-build `else:` 分支真实代码（`index.py:140-144`）与 Plan 1 Task 5 假设一致**：
    ```python
    else:
        with progress_bar("Indexing", total=len(files), enabled=not no_progress) as bar:
            for file_path in files:
                _index_one(file_path, path, store, registry, stats, bar, config)
        _run_bridges(store, stats, config)
    ```
  - `_short_exception_message(producer: str, exc: BaseException)` ✅（两参，Plan 调 `_short_exception_message(ix.name, exc)` 匹配）。
  - 顶部 import 齐全：`Diagnostic`、`Config`、`PurePosixPath`、`logger`、`progress_bar` 全部存在。
- `src/codemap/core/bridge/http_route.py`
  - `HttpRouteBridge.resolve(store) -> BridgeResult`；ClassVar `name="http_route"`。
  - server 侧读 `Symbol.extra["http_route"]`、client 侧读 `Symbol.extra["http_calls"]`，产 `routes_to`（handler→route）与 `calls`（caller→route）边 + `Route`/`Alias`/`Diagnostic`。
- `plugins/codemap-sql/`：**仅 DDL**（CREATE TABLE/VIEW/INDEX），明确忽略 SELECT/INSERT/UPDATE/DELETE。→ 印证 Plan 3 的修正：MyBatis 必须自带 DML 表名抽取。
- `plugins/codemap-java/`：当前 `JavaIndexer` 确为**声明级**——`_Visitor.edges` 恒为 `[]`，全文无 `edges.append`。→ 印证设计 §0「现状缺口①」，Plan 2 用 `JavaScipIndexer` 取代它。

### 2.2 与计划措辞/假设**不一致**项（执行时按此修正，不改变算法与断言）

1. **根 `pyproject.toml` 没有任何「语言插件」的 entry-point 注册行**。根 pyproject 只注册 `_example_lang`+`python`（indexers）与 `http_route`+`python_cross_module`（bridges）。Java/Vue/TS/SQL 等都在各自 `plugins/codemap-*/pyproject.toml` 注册。
   - 影响 **Plan 1 Task 5 Step 5**：在根 pyproject 加 `codemap.project_indexers`/`codemap.emitters` **空占位组**没问题；但 Plan 2 Task 6「从旧 `codemap.indexers` 组移除旧 java 注册」要去改 `plugins/codemap-java/pyproject.toml`，**不是**根 pyproject。
2. `ReadOnlyStore` Protocol **不含** `iter_routes/iter_diagnostics/iter_aliases`（这些只在 `JsonStore` 具体类）。emitter 若只读 symbols/edges 不受影响；若将来 emitter 想读 routes，需收 `JsonStore` 或扩展 Protocol。
3. `index()` 是 `register(app)` 内的**嵌套命令函数**，不能直接 `import index`。但 Plan 1 Task 5 的测试只 import **模块级**辅助函数 `_run_project_indexers`/`_apply_hotspots`（新加的就是模块级），不受影响。
4. `_IndexStats` 是**普通 class 不是 dataclass**，但 `.diagnostics` 字段存在（int 计数），Plan 的 `stats.diagnostics += len(...)` 成立。
5. `JsonStore.open` 是**返回 context-manager 实例的 classmethod**，不是 `@contextmanager` 生成器（仅措辞）。
6. `HttpRouteBridge` 同时用 `http_route`(server)+`http_calls`(client) 两个 key，不是单一 key（Plan 3/4 已分别在 Java 侧写 `http_route`、Vue 侧写 `http_calls`，方向正确）。
7. `importlinter` 现有 3 条 `forbidden` 合约（core / io / indexers 各一条），**无 bridge 专属合约**。Plan 1 Task 5 新增 emitters 合约符合现有模式。
8. **Vue / TypeScript 插件目前完全没有 `http_calls`/axios/fetch 提取逻辑**（grep 零命中）。→ Plan 4 Task 1 是**从零新写**（不是「增强已有」），Plan 0 §4 的审计结论可直接定为「从零写」。

---

## 3. 阻塞分析：哪些被 scip-java 卡住、哪些没有

### 3.1 **不依赖 scip-java，任意环境可立即做**

- **Plan 1 全部**（Task 1–5）：模型枚举、项目级 indexer 协议+注册表、emitter 协议+注册表、git 热点、编排器接入 + import-linter 合约。纯 Python TDD，自给自足。**这是后面一切的地基，强烈建议最先做。**
- **Plan 3 Task 1**（Java 注解抽取，tree-sitter-java，已是依赖）、**Task 3**（MyBatis Mapper XML indexer 的单元测试——`table_refs` + `MyBatisIndexer.index_file` 用手工 XML，自给自足）。
  - ⚠️ 但 Plan 3 的 `_java_method_id` 重建必须**逐字符**等于 scip-java 对同一方法给的 symbol，这点要等 Plan 0 §1 真实符号串才能最终锁定；可先写实现 + 单元测试，留待 Plan 4 golden 联调校验。
- **Plan 4 Task 1**（Vue `http_calls` 从零写）、**Task 2**（`ids` entity_id 派生）、**Task 3**（`AiMemoryEmitter`，测试用手工 seed 符号）、**Task 4**（`enrich` LLM 增强，LLM 用 mock）。这些测试都不需要真实 `.scip`。

### 3.2 **被 scip-java / 真实 `index.scip` 阻塞**

- **Plan 0 全部**（spike：装 scip-java、造样例工程、跑出真实 `index.scip`、记录 §1 符号串格式 / §2 增量能力 / §3 目标工程可构建性 / §4 Vue 现状）。
- **Plan 2 Task 2/4/5/6**：`scip_reader`/`extract_symbols`/`extract_edges`/`JavaScipIndexer` e2e 的测试都以 `tests/fixtures/scip-samples/HelloSpring/index.scip` 为真相源——该 fixture 由 Plan 0 用 scip-java 真实产出。
  - （Plan 2 Task 1 runner、Task 3 symbol_map **可先做**：runner 测试 mock subprocess，symbol_map 是纯字符串→SymbolID；但 Task 3 的 `REAL` 字符串需 Plan 0 §1 实测值替换。）
- **Plan 3 Task 2 Step 5**（Spring 路由经 http_route bridge 成图的集成测试，依赖 fixture `index.scip`）。
- **Plan 4 Task 5**（golden 全栈 fixture + 精度门禁，依赖预生成 `index.scip`）——这是把 Plan 2/3 所有 ⚠️Plan-0 假设做总验收的地方。

---

## 4. 推荐执行顺序（roadmap）

**阶段 A（任意环境，立即可做，零返工风险）**
1. **Plan 1 全部**（地基）。完成后 codemap core 具备：项目级 indexer 钩子、emitter 插件协议、git 热点、新枚举、编排器接入、emitters import-linter 合约。

**阶段 B（需 scip-java 工具链 + 可构建 Java 工程）**
2. **Plan 0** spike：装工具链 → 造 `tests/fixtures/scip-samples/HelloSpring/` 最小 Maven 工程 → 跑出真实 `index.scip` → 写 `docs/spikes/2026-06-23-scip-java-findings.md` 的 §1–§4。
   - **§1 是硬出口**：`OrderService#calculateOrderPrice()` 的逐字符真实 symbol 串、package 描述符形态（Maven 坐标 vs `.` 占位）、重载 disambiguator、**调用关系如何表达**（occurrence symbol_roles 位掩码 / SymbolInformation.relationships / enclosing_range）。直接决定 Plan 2 的 `to_symbolid` 与 `extract_edges`、Plan 3 的 `_java_method_id` 重建。
3. **Plan 2**：用 Plan 0 真实 fixture 与 §1 结论，落地 runner → scip_pb2/reader → symbol_map → extract_symbols/edges → JavaScipIndexer，并替换旧声明级 java 插件。
4. **Plan 3**：注解 → Spring `http_route` 元数据（写进索引期，复用 http_route bridge）→ MyBatis 插件。用真实 fixture 校准 `_java_method_id`。
5. **Plan 4**：Vue `http_calls`（从零）→ ids → AiMemoryEmitter → enrich → golden 全栈 fixture + 精度门禁（high 档 precision ≥ 0.98，接 CI）。

> 也可在阶段 A 顺手把 §3.1 列的「不依赖 scip 的 Plan 3/4 子任务」做掉，但要注意 Plan 3 `_java_method_id`、Plan 2 `symbol_map` 的 `REAL` 串等**含 ⚠️Plan-0 常量**的点，必须等 Plan 0 §1 实测后回填，否则会出现「MyBatis 边 source 悬空 / round-trip 断言失败」。稳妥起见：含 ⚠️ 的常量留到阶段 B。

---

## 5. 执行规范提醒（给接手的会话/Agent）

- 每个 plan 顶部都标了 **REQUIRED SUB-SKILL：superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans**，按其逐 task / 逐 step 执行，步骤用 `- [ ]` 跟踪。
- 全程 **TDD**：先写失败测试 → 跑确认 FAIL → 写实现 → 跑确认 PASS → commit。Plan 里每步都给了具体命令与 Expected。
- **门禁不降标**：`ruff check`、`mypy --strict`、`pytest --cov-fail-under=80`、`lint-imports`（import-linter）、bench。新代码一并纳入。
- **不在 main 直接实现**：先开 worktree 或 feature 分支（superpowers:using-git-worktrees）。本次用户选择「跳过」是因为本轮只写结论、不实现。
- **commit 署名**：按全局规则追加两条 `Co-Authored-By`（Claude 在前、用户实时取 `git config user.name/email` 在后）。
- **降级铁律**：critical（scip-java 构建失败）之外，任何单层失败都不能让整体 L1 产出失败——保留上一份好索引、记 diagnostic 继续。

---

## 6. 接手 checklist（换环境后从这里开始）

- [ ] 拉取/同步 codemap 仓库到新环境，确认本文件在 `docs/spikes/`。
- [ ] 装 scip-java + maven（或 gradle）+ protoc/grpcio-tools（见 §1 命令）。
- [ ] 准备一个可 `mvn -DskipTests compile` 通过的目标 Java 工程（或用 Plan 0 Task 2 的 HelloSpring 最小样例）。
- [ ] 开 worktree / feature 分支（不在 main 上写）。
- [ ] 若想零等待：先做 **Plan 1 全部**（阶段 A，不需以上工具）。
- [ ] 工具链就绪后做 **Plan 0**，把 `2026-06-23-scip-java-findings.md` §1–§4 用实测证据写满。
- [ ] 按 §1 findings 回填 Plan 2/3 的 ⚠️ 常量，再依次推进 Plan 2 → 3 → 4。
- [ ] 全链跑通后用 Plan 4 golden 精度门禁验收，接入 CI。

---

## 附：本轮已确认的关键事实索引（避免接手者重复勘察）

- 旧 `JavaIndexer` 声明级、零 Edge：`plugins/codemap-java/src/codemap_java/indexer.py`（`_Visitor.edges=[]`，无 append）。
- full-build 编排接入点：`src/codemap/cli/commands/index.py:140-144`（`else:` 块，`_run_bridges` 之后是 Plan 1 追加 hotspots/emitters 的位置）。
- http_route bridge 读 `extra["http_route"]`(server) / `extra["http_calls"]`(client)：`src/codemap/core/bridge/http_route.py`。
- DDL-only SQL 插件：`plugins/codemap-sql/src/codemap_sql/indexer.py`（docstring 明示忽略 DML）。
- Vue/TS 无 http_calls：`plugins/codemap-vue`、`plugins/codemap-typescript` grep 零命中。
- import-linter 合约：`pyproject.toml`（core/io/indexers 三条 forbidden，无 bridge 合约）。
