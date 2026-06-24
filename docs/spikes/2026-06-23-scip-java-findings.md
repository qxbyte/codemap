# scip-java spike findings (Plan 0)

> 创建时间：2026-06-24
> 状态：**部分完成** —— §0/§3/§4 已落定；§1/§2 阻塞，等本机 scip-java 工具链就绪
> 关联：spec `2026-06-23-codemap-l1-知识图谱重构-design.md`、`plan-0-验证spike`、交接文档 `2026-06-24-codemap-refactor-execution-readiness.md`

---

## §0. 环境勘察与工具链状态

**本机（xueqiang的 MacBook Pro, Darwin 25.5.0, arm64）：**

| 工具 | 状态 | 备注 |
|---|---|---|
| Java 17 | ✅ `17.0.17 LTS` (`/usr/bin/java`) | Maven 工程构建用 |
| Python 3.13 | ✅ `.venv/bin/python` | 项目自带 venv |
| `mvn` | ✅ `/opt/homebrew/bin/mvn` (Homebrew) | 已验证可编译 fixture |
| `scip-java` | ❌ **未安装** | 本轮被代理速度阻塞（见下） |
| `cs` (coursier) | ❌ 未安装 | 同上 |
| `protoc` | ❌ 未安装 | Plan 2 生成 `scip_pb2.py` 用，或 `grpcio-tools` 替代 |
| `grpcio-tools` (PyPI) | ⏳ 待装于 `.venv` | 受 PEP 668 阻挡装到系统 Python，改用 venv |

**安装阻塞证据：**

- `brew install coursier/formulas/coursier` 跑了 5+ 分钟没出任何输出 → kill。
- 直接 `curl -fLo cs.gz https://github.com/coursier/coursier/releases/latest/download/cs-aarch64-apple-darwin.gz`（21 MB）→ 90 秒只下了 2.3 MB（平均约 30 KB/s）→ 超时退出。
- HTTPS 通过 SOCKS5 (`127.0.0.1:7890`) 本身可用（`curl https://repo.maven.apache.org/maven2/` → 200 OK，`curl https://github.com` → 200 OK），代理服务有效，**但带宽极低**，scip-java jar 包（数十 MB）实际下载不下来。
- DNS：系统 nameserver 指向 `198.18.0.2`（Clash/Surge 类代理的 fake-IP 网段）；`nslookup` 直发 UDP 53 失败属于代理软件默认只代理 TCP 的预期行为，对 HTTPS 应用无影响。

**下次推进 §1/§2 的两个可行路径：**

1. 改进代理速度（换节点 / 直连 / 公司代理）后重跑 `cs install scip-java`。
2. 在带宽好的环境下载 scip-java，scp 到本机后直接 `mv` 到 `~/.local/bin/scip-java`。

---

## §1. 真实 SCIP symbol 字符串格式（HARD GATE for Plan 2/3）

> 状态：**PENDING**（被 §0 工具链阻塞）

待 scip-java 装好后，在 `tests/fixtures/scip-samples/HelloSpring/` 目录执行：

```bash
cd tests/fixtures/scip-samples/HelloSpring
scip-java index --output index.scip -- compile
scip print --json index.scip > index.scip.json
grep -o '"symbol":[^,]*' index.scip.json | sort -u | head -40
```

需要在本节回答的问题（来自 plan-0 Task 1 Step 5）：

- [ ] `com.example.hellospring.service.OrderService#calculateOrderPrice(long)` 的**逐字符**真实 SCIP symbol 串
- [ ] package 描述符到底用什么：Maven `group/artifact version` 还是 `.` 占位
- [ ] 方法 disambiguator（重载场景；本 fixture 暂无重载，可造一个）
- [ ] 调用关系怎么表达：`Occurrence.symbol_roles` 位掩码？`SymbolInformation.relationships`？还是按方法 range 内对其它 symbol 的非定义引用推断？
- [ ] 定义 range 在 `occurrence.range` 还是 `SymbolInformation` 的某字段？是否填 `enclosing_range`？

**直接消费方：**
- Plan 2 `plugins/codemap-java/src/codemap_java/symbol_map.py` 的 `to_symbolid()` 实测 round-trip 用例
- Plan 2 `extract_edges` 里 `_enclosing_method()` 的实现策略选择
- Plan 3 `plugins/codemap-mybatis` 的 `_java_method_id(namespace, method)` 重建，必须**逐字符**等于 scip-java 给同一方法的 symbol，否则 MyBatis 边的 source 悬空

---

## §2. scip-java 增量索引能力

> 状态：**PENDING**（被 §0 工具链阻塞）

待 scip-java 装好后执行：

```bash
cd tests/fixtures/scip-samples/HelloSpring
time scip-java index --output index_full.scip -- compile
# 改一处 OrderService.java 加一行无害日志
time scip-java index --output index_inc.scip -- compile
```

需要在本节回答的问题：

- [ ] (a) scip-java 支持增量/部分索引 → Plan 2 可做受影响单元重索引
- [ ] (b) 仅全量 → spec §5.3② 退化为「每次全量重跑 scip-java + codemap 侧按 sha256 diff」；正确性不变、代价记录在案

**直接消费方：** Plan 2 `JavaScipIndexer.index_project()` 的增量策略；编排器 `_do_incremental` 路径里项目级 indexer 的调用频率（当前 Plan 1 Task 5 实现是每次 incremental 都全量重跑，符合 (b) 假设）。

---

## §3. 目标企业工程可构建性

> 状态：**N/A** —— 本机无目标企业工程

Plan 0 Task 3 的目的是验证「真实业务工程能否稳定 mvn compile + scip-java index」。本机只有 `tests/fixtures/scip-samples/HelloSpring/`（开发期最小 fixture），未持有任何目标企业工程。

**判断与后续动作：**

- 本节的结论只能在能访问真实业务工程的环境里二次评估（开发机 / CI runner）。
- 一旦目标工程接入，本节需补：JDK 版本、是否多模块（aggregator pom）、私服/离线依赖能否拉取、构建总耗时、scip-java 在该工程上是否成功产 `index.scip`。
- 不阻塞 Plan 1（已完成）、Plan 2 算法本身（用 HelloSpring fixture 验证）、Plan 3 框架 bridge 算法（同上）。但**精度门禁**（Plan 4 Task 5）的最终意义需在真实工程上跑一次校准。

---

## §4. codemap-vue / codemap-typescript 的 http_calls 现状

> 状态：**已落定**

### 4.1 实测

```bash
# 仓库根
grep -rn "http_calls\|http_route\|axios\|fetch" \
    plugins/codemap-vue plugins/codemap-typescript \
    src/codemap/core/bridge/http_route.py
```

实测命中（2026-06-24，分支 `feat/l1-knowledge-graph`）：

- `plugins/codemap-vue/README.md:68` — 文档里仅 1 行示例 symbol（无实现）
- `src/codemap/core/bridge/http_route.py` — bridge 自身的 5 处（`extra["http_route"]` server 侧、`extra["http_calls"]` client 侧，以及类型注解）

实测 **`plugins/codemap-vue/src/`、`plugins/codemap-typescript/src/` 的实现代码中零命中 `axios` / `fetch` / `http_calls` / `http_route`**。

### 4.2 代码核对

- `plugins/codemap-vue/src/codemap_vue/indexer.py` —— Vue SFC indexer：用 tree-sitter-vue 不可得，所以走「SFC 切片 + 内嵌 JS/TS 走 tree-sitter-javascript / tree-sitter-typescript」。访问者只采集：top-level 函数、类（含方法）、模块级 `const/let/var` 声明。**不识别**调用表达式中的 `axios.<verb>(...)` 或 `fetch(...)` 字面量。
- `plugins/codemap-typescript/src/codemap_typescript/indexer.py` —— 同模式（直接走 tree-sitter-typescript，无 SFC 切片）。

### 4.3 结论 & Plan 4 起点

- **从零写**（不是「增强已有」）。Plan 4 Task 1 文档里也已写了「实现 http_calls 抽取」，本节是其前置事实确认。
- 实现位点：在 vue/typescript indexer 的 AST 遍历里加调用表达式访问；识别 `axios.<verb>` / `this.$axios.<verb>` / `fetch` / `useFetch`（按团队约定扩展），把 `{method, url, confidence}` 累加到所在方法/组件符号的 `extra["http_calls"]`。
- 置信度：纯字面量 url → `medium`；含模板拼接 / 变量 → `low`；动态计算 → 不建边（宁缺毋滥，符合 spec §5.1）。
- 下游：现成的 `HttpRouteBridge` 已经读 `extra["http_calls"]`，只要 Vue 侧产出格式正确，Plan 3 Task 2 Java 侧产出 `extra["http_route"]` 后 bridge 自动跨语言连边。

---

## 接手 Checklist（下一轮）

- [ ] 把 §0 的代理速度问题解决后跑 `cs install scip-java`（或手工放 scip-java 二进制到 `~/.local/bin/`）。
- [ ] 跑 `scip-java index` 出 `tests/fixtures/scip-samples/HelloSpring/index.scip`，把 §1 的 5 个问题用实测证据写满。
- [ ] 跑 §2 的全量+增量两次 `time scip-java index`，二选一。
- [ ] 把 fixture 工程 + `index.scip` + 本 findings 文档一并 commit（`spike: capture real scip-java output format on HelloSpring sample`）。
- [ ] 按 §1 的 `REAL` symbol 字符串回填 Plan 2 `symbol_map.py` 测试与 Plan 3 `_java_method_id()` 重建逻辑。
- [ ] 继续 Plan 2 → 3 → 4。
