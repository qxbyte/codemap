# CodeMap

[English](./README.md) · **简体中文**

> 面向 AI Agent 的代码索引 —— 不必全项目搜索即可精确导航。

CodeMap 为代码库构建一份**确定性**的、基于 AST 的索引,让 AI Agent
(Claude Code、Cursor、Codex 等)无需 grep 整个项目即可拿到调用链、
路由映射与跨文件关联。索引过程是静态的、快速的、可复现的 —— **索引
路径上不依赖任何 LLM**。

**状态**:0.3.1 稳定版。已发布到 PyPI,主包名 `codemap-core`,
另含 17 个 `codemap-<lang>` 语言插件 + 2 个框架/输出插件
(`codemap-mybatis`、`codemap-aimemory`,0.3.0 新增;
0.3.1 加 `codemap llm config` CLI 与国产模型 endpoint 速查)。

## 产物说明

`codemap index` 在项目根写两个并列目录:

```
<project>/
├── .codemap/        ← 确定性索引(被 `codemap …` 命令查询)
└── .ai-memory/      ← 四层记忆模型 L1 输出(被 AI Agent 直接消费)
```

### `.codemap/` — 7 个 JSON 文件

| 文件 | 内容 |
|---|---|
| `symbols.json` | 所有符号,按 `SymbolID` 索引。含 `kind / language / file / range / signature / annotations / confidence / extra`(语言相关字段:`pending_calls / http_route / supertypes / imports / params / return_type / change_count_90d / …`)|
| `edges.json` | 有向关系:`calls / extends / implements / overrides / references / routes_to / maps_to / imports / accesses_table`,每条带 `confidence` ∈ {`high`, `medium`, `low`} |
| `routes.json` | 由 `http_route` bridge 从 `extra["http_route"]` 铸造的 HTTP 路由 |
| `aliases.json` | 中间符号 ↔ 真实符号的映射(如 route → handler) |
| `manifest.json` | 项目元数据 + 索引器/桥接器版本 + 文件 sha256/mtime |
| `diagnostics.json` | 索引期收集的 warning / error |
| `.lock` | 进程间写锁;勿动 |

### `.ai-memory/` — 四层记忆模型(部分由 `codemap-aimemory` 产出)

`codemap-aimemory` 负责 L0+L1(每次 `codemap index` 都写)；L2+L3
(`knowledge/` 目录)由[兄弟工具](#与-specode-distill--task-swarm-的集成)
`specode-distill` 和 `task-swarm` 产生。AI Agent 直接读这棵树。稳定的
`entity_id`(`fn-* / cls-* / tbl-* / mod-*`)从 SCIP `SymbolID` 派生。

```
.ai-memory/
├── project.yml              ← L0(codemap-aimemory 0.3.2+)
│                              技术栈 / 依赖 / git remote / 顶级目录 /
│                              关键 config 文件 — best-effort 自动探测
│
├── entities/                ← L1(codemap-aimemory 0.3.0+)
│   ├── functions.yml          fn-/cls- 实体:calls / called_by /
│   │                          related_tables / signature / line_range /
│   │                          confidence / change_count_90d /
│   │                          business_meaning
│   ├── tables.yml             tbl-* 表实体
│   ├── files.yml              file-* 文件条目
│   └── modules.yml            mod-* 按 file 聚合(0.3.3+):
│                              {id, path, language, fn_count, cls_count,
│                               functions[], classes[]}
│
├── relations/               ← L1
│   ├── call-graph.yml         `{from, to, type=calls, confidence}`
│   ├── table-relations.yml    `{from, to, type=accesses_table, confidence}`
│   └── rule-constraints.yml   空占位符(由 L2 维护)
│
├── enrichment/              ← L1 可选:LLM 生成的解释
│   └── <sha1[:12]>.yml        `{symbol_id, business_meaning,
│                                related_rules, confidence:"llm",
│                                source_model, generated_at}`
│
├── _global/                 ← L1↔L2/L3 跨层 lookup(codemap-aimemory 0.3.4+)
│   └── entities.yml           跨链视图:每个 entity_id(code 或 knowledge)
│                              带 `source` ∈ {code, knowledge, both} +
│                              `knowledge_refs`(哪些 knowledge yml
│                              提到这个实体)。`codemap recall` 的底层
│                              索引。
│
├── _semantic/               ← P1-3,可选:由 codemap-semantic-index 写
│   ├── chunks.json            chunked text + metadata(模型无关)
│   ├── vectors.npy            (n_chunks, 1024) float32(模型相关)
│   ├── model_id.txt           当前 active backend 指纹
│   └── manifest.json          text_hash → chunk_id(增量 embed 用)
│
└── knowledge/               ← L2 + L3(**codemap 本身不写**;
                              由 specode-distill / task-swarm 产生;
                              codemap-aimemory 只读它构建
                              _global/entities.yml 并支撑 recall)
    ├── rules/    rule-*.yml         L2 业务规则 / 机制
    ├── business/ biz-*.yml          L2 业务流程 / 功能页
    ├── modules/  mod-*.yml          L2 模块地图(表 / 调用链)
    ├── cases/    case-*.yml         L3 历史实现案例
    └── pitfalls/ pit-*.yml          L3 可复用失败 / 修复经验
```

两跳展开:Java 方法 `maps_to` 一个 `sql_mapping`,后者 `accesses_table` 某张表 → 该表自动出现在方法的 `related_tables` 中。所以 `fn-selectByUser.related_tables = [tbl-sf_coupon]` 不需要 Agent 自己走链。

---

### 与 `specode-distill` / `task-swarm` 的集成

codemap-aimemory 拥有 L0+L1;**L2+L3(`knowledge/`)来自
[pluginhub](https://github.com/qxbyte/pluginhub) 家族的兄弟工具**。
集成是单向松耦合的——codemap 不 import 其它工具,只在 yml 存在时
读取它们的产物:

| 层 | 写入工具 | 触发时机 |
|---|---|---|
| L0 `project.yml` | `codemap-aimemory`(本工具) | 每次 `codemap index` |
| L1 `entities/*`、`relations/*`、`enrichment/*` | `codemap-aimemory`(本工具) | 每次 `codemap index`(enrichment 是 opt-in:`codemap enrich`) |
| L1↔L2/L3 `_global/entities.yml` | `codemap-aimemory`(本工具) | 每次 `codemap index`,扫 `knowledge/*.yml`(若存在) |
| L2/L3 `knowledge/{rules,business,modules,cases,pitfalls}/*.yml` | `specode-distill`(`pluginhub` 插件,specode 3.0+；3.3.1 经 AI-EDS v0.9 痛点 #14 方案 D 把 `CLAUDE.md / AGENT.md` 路径写入 `requirements.md`；3.3.2 加 cache 与 marketplace drift 提示；3.4.0 加 autonomous-mode defaults 供 CI / 无人值守使用) | 用户运行 `/specode:specode-distill <slug>`,或在 specode acceptance 末尾选"立即沉淀" |
| L3 `knowledge/cases/case-*.yml` + `knowledge/pitfalls/pit-*.yml` | `task-swarm`(`pluginhub` 插件,0.7+ 通过 `codemap knowledge write` 写盘；0.7.3 + 0.7.4 在每个 subagent `task.md` 中列出 `CLAUDE.md / AGENT.md` 路径 + inbox drop `_PROJECT_AGENT_DOCS.md` sentinel；0.8.0 加 `init` dedupe `--on-existing` flag) | 每次 `task_swarm.py resolve` 成功收尾时自动 |

每次 `specode-distill` / `task-swarm` 写入时**还会同步产出**一份双胞胎
markdown:`<project_root>/knowledge-base/<category>/<id>.md`(与 yml
同 stem)。md 双产保留 yml 字段化丢失的散文 / ascii 流程图 /
表格,是未来 embedding indexer 的高质量切片源。**codemap 本身今天不读
`knowledge-base/`**——`codemap recall` 走的是 yml 一侧;md 是给人读和
未来 P1-3 语义搜索用的。

**用 `codemap recall '<query>'` 查询统一视图**(代码侧实体命中 +
对每个 `knowledge/*.yml` 的 token 重合度排序)。这是 specode 2.1+ 从
requirements phase 调用的入口——在草拟新 spec 之前把"已知约束 /
历史坑"注入上下文。完整 agent 端工作流见 `docs/integration.md`(规划中)。

`knowledge/` 不是 codemap 运行的必要条件。从未跑过 `specode-distill` /
`task-swarm` 的项目,`_global/entities.yml` 只会列代码侧实体
(`source: code`),`codemap recall` 返回命中实体 + 空 `knowledge: []`。

## LLM 配置(可选)

核心索引**永远不调 LLM**——`codemap index` 不会触达任何 API。只有 `codemap-aimemory` 的 `codemap enrich` 命令会写 `enrichment/` 覆盖层,且**必须你主动调用**。api-key 的存在 = LLM 开关本身:没配 key 时 `codemap enrich` 直接报错退出,不会偷偷调 LLM 烧 quota。

三种配置方式,**第一个非空优先**:

1. **CLI flag** — `--api-key`、`--base-url`、`--model`、`--backend`
2. **环境变量** — `CODEMAP_LLM_API_KEY`(回退 `ANTHROPIC_API_KEY`、`OPENAI_API_KEY`);`CODEMAP_LLM_BASE_URL`(回退 `OPENAI_BASE_URL`、`ANTHROPIC_BASE_URL`);`CODEMAP_LLM_MODEL`;`CODEMAP_LLM_BACKEND`
3. **持久化文件配置** — `~/.config/codemap/llm.yaml`(由 `codemap llm config set/unset/show` 管理,写入 `chmod 600`)
4. 内置默认 — backend `openai`,model `gpt-4o-mini`

### 常见国产/开源大模型 endpoint(都用 `--backend openai`)

| 厂商 | 模型示例 | Base URL |
|---|---|---|
| OpenAI | `gpt-4o-mini` | `https://api.openai.com/v1` *(默认)* |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| 智谱 GLM | `glm-4-flash` | `https://open.bigmodel.cn/api/paas/v4/` |
| MiniMax | `abab6.5s-chat` | `https://api.minimax.chat/v1` |
| 月之暗面 Kimi | `moonshot-v1-8k` | `https://api.moonshot.cn/v1` |
| 阿里通义 | `qwen-plus` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 小米 MiMo | `mimo-large` | *(以厂商文档为准;走 OpenAI 兼容协议)* |
| Ollama(本地) | `llama3` | `http://localhost:11434/v1` — 用 `--backend ollama`(不需要 key)|
| Anthropic 原生 | `claude-sonnet-4-5` | *(用 `--backend anthropic`;需 `pip install codemap-aimemory[llm]` 装 SDK)* |

DeepSeek 示例:

```bash
codemap llm config set base-url https://api.deepseek.com/v1
codemap llm config set api-key sk-xxx
codemap llm config set model deepseek-chat
codemap enrich .
```

> 👉 **想直接动手?** [`INSTALL.zh-CN.md`](./INSTALL.zh-CN.md) 是完整
> 安装指南 —— 覆盖 `pipx` / `uv tool` / `pip` 三种装法、语言插件注入、
> 离线分发、常见问题排查,以及一份逐字记录的干净机器验证日志。

---

## 目录

- [核心原则](#核心原则)
- [安装](#安装)
  - [1. 主 CLI](#1-主-cli)
  - [2. 可选 extras](#2-可选-extras)
  - [3. 语言插件](#3-语言插件)
  - [4. 本地克隆(开发模式)](#4-本地克隆开发模式)
  - [4b. 从 git 安装(跟 main / 锁 commit)](#4b-从-git-安装跟-main--锁-commit)
  - [5. 系统要求](#5-系统要求)
- [验证](#验证)
- [命令](#命令)
- [配置文件](#配置文件)
- [内置索引器与桥接器](#内置索引器与桥接器)
- [架构](#架构)
- [写插件](#写插件)
- [性能](#性能)
- [文档](#文档)
- [贡献](#贡献)
- [许可证](#许可证)

---

## 核心原则

1. **静态分析优先,LLM 仅作消费者** —— 索引必须确定性、可复现。
2. **分层防御,承认不确定性** —— 把 confidence 暴露给 Agent,不要瞎猜。
3. **跨资产桥接是核心价值** —— 非源码资产(XML / YAML / IDL)通过与
   语言相同的协议接入。
4. **可演进路径** —— CLI → MCP Server → Agent CLI,每步独立有价值。
5. **生态兼容** —— SCIP 用于符号,MCP 用于工具。
6. **语言中立** —— 任何语言/框架在系统中地位完全对等,Indexer 与
   Bridge 全部通过同一套插件协议注册(详见
   [ADR-L001](docs/adr/0011-language-neutrality.md))。

## 安装

### 1. 主 CLI

```bash
# 推荐:pipx 提供环境隔离,装好后系统级有 `codemap` 命令
pipx install codemap-core

# 普通 pip(建议装到 venv 里)
pip install codemap-core

# 或用 uv
uv tool install codemap-core
```

### 2. 可选 extras

```bash
# `--watch` 模式需要 watchdog
pip install "codemap-core[watch]"
pipx install "codemap-core[watch]"

# 开发工具(pytest、lint、mypy、import-linter、benchmark 等)
pip install "codemap-core[dev]"
```

### 3. 语言插件

每个非 Python 的语言 indexer 都作为**独立 PyPI 发行包**发布。
若主包是用 `pipx` 装的,用 `pipx inject` 把插件装进同一个隔离 venv:

```bash
# 17 个语言一次性装齐
pipx inject codemap codemap-typescript codemap-javascript codemap-vue \
                    codemap-java codemap-jsp codemap-go \
                    codemap-rust codemap-swift codemap-kotlin \
                    codemap-ruby codemap-php codemap-sql \
                    codemap-bash codemap-c codemap-cpp \
                    codemap-csharp codemap-scala

# 0.3.0 新增的两个插件 —— 框架感知 (Spring/MyBatis 调用图) 与
# 四层记忆模型 L1 输出 (.ai-memory/)。完全可选,codemap-core 不依赖。
pipx inject codemap codemap-mybatis codemap-aimemory
```

若主包是用 `pip` 装的:

```bash
pip install codemap-typescript codemap-javascript codemap-vue \
            codemap-java codemap-jsp codemap-go codemap-rust \
            codemap-swift codemap-kotlin codemap-ruby codemap-php \
            codemap-sql codemap-bash codemap-c codemap-cpp \
            codemap-csharp codemap-scala

# 框架/输出插件
pip install codemap-mybatis codemap-aimemory
```

只装单个插件也可以:

```bash
pipx inject codemap codemap-typescript   # 或 pip install codemap-typescript
```

每个插件都声明依赖 `codemap-core`,所以如果没装主包,pip 会一起拉取。
装好后 `codemap doctor` 会列出所有已安装的插件,与内置 indexer
**地位完全一致** —— 详见[写插件](#写插件)。

### 4. 本地克隆(开发模式)

```bash
git clone https://github.com/qxbyte/codemap.git
cd codemap

# 可编辑安装 + 完整开发工具链
pip install -e ".[dev,watch]"

# 可选:可编辑安装所有语言插件
pip install -e plugins/codemap-typescript
pip install -e plugins/codemap-java
pip install -e plugins/codemap-go
pip install -e plugins/codemap-rust
pip install -e plugins/codemap-swift
pip install -e plugins/codemap-kotlin
pip install -e plugins/codemap-ruby
pip install -e plugins/codemap-php
pip install -e plugins/codemap-sql
pip install -e plugins/codemap-bash
pip install -e plugins/codemap-c
pip install -e plugins/codemap-cpp
pip install -e plugins/codemap-csharp
pip install -e plugins/codemap-scala
```

### 4b. 从 git 安装(跟 main / 锁 commit)

如果想用 `main` 上未发布的改动、或锁定到具体 commit,git URL 形式
仍然可用:

```bash
# 跟随 main
pip install git+https://github.com/qxbyte/codemap.git
pipx install git+https://github.com/qxbyte/codemap.git

# 锁定到具体 commit
pip install git+https://github.com/qxbyte/codemap.git@2c3ed45

# 单独装某个子目录里的语言插件
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-typescript"
```

### 5. 系统要求

| 项 | 要求 |
|---|---|
| Python | ≥ 3.11(项目以 3.13 开发) |
| 操作系统 | macOS / Linux(Windows 上 `--watch` 可能走 polling fallback) |
| 网络 | 安装时需要(拉取 `tree-sitter-typescript` 等) |

---

## 验证

```bash
codemap --version      # → 0.1.0
codemap --help         # 显示全局选项与子命令
codemap doctor         # 列出已注册的 indexer / bridge,以及 .codemap/ 状态
```

成功装好主包 + TypeScript 插件后,`codemap doctor` 输出:

```
$ codemap doctor
CodeMap 0.1.0
project_root: /your/path

                   Registered indexers
┃ name          ┃ version ┃ languages  ┃ file_patterns ┃
┃ _example_lang │ 0.1.0   │ example    │ *.example     │
┃ python        │ 0.1.0   │ python     │ *.py, *.pyi   │
┃ typescript    │ 0.1.0   │ typescript │ *.ts, *.tsx   │
┃ java          │ 0.1.0   │ java       │ *.java        │
┃ go            │ 0.1.0   │ go         │ *.go          │
┃ rust          │ 0.1.0   │ rust       │ *.rs          │
┃ swift         │ 0.1.0   │ swift      │ *.swift       │
┃ kotlin        │ 0.1.0   │ kotlin     │ *.kt, *.kts   │
┃ ruby          │ 0.1.0   │ ruby       │ *.rb          │
┃ php           │ 0.1.0   │ php        │ *.php         │
┃ sql           │ 0.1.0   │ sql        │ *.sql, *.ddl  │
┃ bash          │ 0.1.0   │ bash       │ *.sh, *.bash, *.bats │
┃ c             │ 0.1.0   │ c          │ *.c, *.h      │
┃ cpp           │ 0.1.0   │ cpp        │ *.cpp, *.cc, *.cxx, *.hpp, *.hh, *.hxx │
┃ csharp        │ 0.1.0   │ csharp     │ *.cs, *.csx   │
┃ scala         │ 0.1.0   │ scala      │ *.scala, *.sc │

           Registered bridges
┃ name                 ┃ version ┃ requires ┃
┃ http_route           │ 0.1.0   │ -        │
┃ python_cross_module  │ 0.1.0   │ -        │
```

---

## 命令

完整参考:[`docs/cli.md`](docs/cli.md)。

```bash
# 索引项目(写 .codemap/)
codemap index /path/to/project
codemap index . --rebuild               # 丢弃旧索引重建
codemap index . --incremental           # 只重解析 sha256 变化的文件
codemap index . --watch                 # 监听变化,持续增量索引
codemap index . --dry-run               # 只报告会做什么,不写盘

# 诊断
codemap doctor                          # 插件 + 索引健康检查
codemap diagnostics --severity error    # 查看 warning / error
codemap config show                     # 显示合并后的有效配置

# 查询
codemap search login -n 5
codemap get '<symbol-id>'
codemap callers '<symbol-id>' --depth 2
codemap callees '<symbol-id>'
codemap trace --from '<id>' --depth 5
codemap trace --from '<id>' --to '<id>' # 最短路径
codemap routes                          # http_route 桥接器产出的路由

# 知识检索 — 0.3.5+(codemap-aimemory 插件)
# 扫 .ai-memory/knowledge/*.yml(由 specode-distill / task-swarm 写)
# 按 token 重合度排序;返回 top-K 相关知识。
# 设计上由 specode 在 requirements phase 开头自动调用。
codemap recall '<query>'                                # 默认 top-k 5,yaml 输出
codemap recall '<query>' -p /abs/project -k 10 -o json  # 显式项目 + json
codemap recall '<query>' -t rules,pitfalls              # 按类别过滤
codemap recall --from-spec requirements.md              # 0.3.6+:用 spec 文件作为 query
codemap recall '<query>' --with-content                 # 0.4.0+:返回每个 hit 含 rule/pit/case 核心字段
# 0.4.0 起每个结果都带 `freshness_score`/`ranked_score`/`stale`;
# 同 token score 时 fresh hit 排在 stale 前面(180 天半衰期 + 代码 churn 衰减)。
# 装了 `codemap-semantic-index` 插件(P1-3, v0.4.2 起),recall 自动变 hybrid
# (token + embedding) + RRF 融合 + freshness 衰减。

# 语义召回(需要 opt-in `codemap-semantic-index` 插件,P1-3)
codemap embed install               # 交互选模型;默认下载 Qwen3-Embedding-0.6B (1.2GB)
codemap embed                       # 增量 embed knowledge-base/*.md
codemap embed --rebuild             # 全量重算
codemap embed backend set --provider qwen --api-key sk-xxx  # 切云端千问 embedding

# 机器可读输出:所有命令都支持 --json
codemap --json callers '<symbol-id>'
```

退出码遵循 `sysexits.h`(ADR-005),详见
[`docs/cli.md`](docs/cli.md#exit-codes)。

---

## 配置文件

项目级配置位于 `.codemap/config.yaml`(可以提交也可以加入 .gitignore)。
用户级覆盖在 `~/.config/codemap/config.yaml`,合并顺序:**默认 → 用户级
→ 项目级**,命令行选项再覆盖以上三层。

```yaml
# .codemap/config.yaml
storage:
  backend: json          # json | sqlite(sqlite 留给后续 Sprint)

index:
  ignore: []             # fnmatch 模式,匹配文件名 + 项目相对路径
  max_file_bytes: 10485760
  follow_symlinks: false

indexers:
  enabled: all           # "all" 或显式 indexer 名字列表
  disabled: []           # 减法操作

bridges:
  enabled: all
  disabled: []
```

完整参考:[`docs/configuration.md`](docs/configuration.md)。
跑 `codemap config show` 可看合并后的有效配置以及每个值来自哪一层。

---

## 内置索引器与桥接器

| Indexer | 文件类型 | 提供方 | 状态 |
|---|---|---|---|
| `python` | `*.py`, `*.pyi` | 主仓库 | 首发实现,dogfooding |
| `typescript` | `*.ts`, `*.tsx` | [`plugins/codemap-typescript/`](plugins/codemap-typescript) | 独立插件包 |
| `java` | `*.java` | [`plugins/codemap-java/`](plugins/codemap-java) | 独立插件包 |
| `go` | `*.go` | [`plugins/codemap-go/`](plugins/codemap-go) | 独立插件包 |
| `rust` | `*.rs` | [`plugins/codemap-rust/`](plugins/codemap-rust) | 独立插件包 |
| `swift` | `*.swift` | [`plugins/codemap-swift/`](plugins/codemap-swift) | 独立插件包 |
| `kotlin` | `*.kt`, `*.kts` | [`plugins/codemap-kotlin/`](plugins/codemap-kotlin) | 独立插件包 |
| `ruby` | `*.rb` | [`plugins/codemap-ruby/`](plugins/codemap-ruby) | 独立插件包 |
| `php` | `*.php` | [`plugins/codemap-php/`](plugins/codemap-php) | 独立插件包 |
| `sql` | `*.sql`, `*.ddl` | [`plugins/codemap-sql/`](plugins/codemap-sql) | 独立插件包(仅 DDL) |
| `bash` | `*.sh`, `*.bash`, `*.bats` | [`plugins/codemap-bash/`](plugins/codemap-bash) | 独立插件包 |
| `c` | `*.c`, `*.h` | [`plugins/codemap-c/`](plugins/codemap-c) | 独立插件包 |
| `cpp` | `*.cpp`, `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.hxx` | [`plugins/codemap-cpp/`](plugins/codemap-cpp) | 独立插件包 |
| `csharp` | `*.cs`, `*.csx` | [`plugins/codemap-csharp/`](plugins/codemap-csharp) | 独立插件包 |
| `scala` | `*.scala`, `*.sc` | [`plugins/codemap-scala/`](plugins/codemap-scala) | 独立插件包 |
| `_example_lang` | `*.example` | 主仓库 | 参考实现 / 烟雾测试 |

| Bridge | 作用 |
|---|---|
| `http_route` | 从 `Symbol.extra["http_route"]` 与 `["http_calls"]` 元数据生成 `scip-route` 中介符号,语言无关地把客户端调用方连接到服务端 handler |
| `python_cross_module` | 把 Python indexer 产出的合成 `scip-python . . . <module>/<leaf>.` 目标解析到本仓库内的真实符号(当对应文件在索引中时) |

加新语言?**不需要 PR 主仓库** —— 详见[写插件](#写插件)。

---

## 架构

```
cli  →  core  ←  indexers
        ↑          ↑
        └── io ────┘
        ↑
        mcp
```

- **core** —— 纯业务逻辑、Pydantic 数据模型、SymbolID(SCIP 格式)、
  调用图算法(`walk_chain`、`shortest_path`)
- **io** —— 持久化适配器(目前 JSON,大规模时切 SQLite)
- **indexers** —— 可插拔语言/资产索引器,通过 `codemap.indexers`
  entry-point 组发现
- **bridges** —— 可插拔跨语言桥接器,通过 `codemap.bridges`
  entry-point 组发现
- **cli** —— Typer 命令入口
- **mcp** —— MCP server(后续 Sprint)

`pyproject.toml` 内的 `import-linter` 契约强制依赖方向
`cli → core ← indexers` 与 `cli → core ← io`,任何 PR 违反即阻塞。

---

## 写插件

CodeMap 的 indexer 与 bridge 都是 plugin-first 设计。**加新语言就是
做一个独立 PyPI 包**,主仓库无需改一行代码。`plugins/` 下的
`codemap-typescript` 就是参考实现:

```toml
# your-plugin/pyproject.toml
[project.entry-points."codemap.indexers"]
yourlang = "codemap_yourlang:YourLangIndexer"
```

这一行就是唯一的耦合点。`pip install your-plugin` 之后你的 indexer
就出现在 `codemap doctor` 列表中,与内置 indexer **地位完全一致**。

分步指南:[`docs/plugin-guide.md`](docs/plugin-guide.md)。
参考实现:[`plugins/codemap-typescript/`](plugins/codemap-typescript)。

---

## 性能

基线数字(中位数,M 系列单核,索引 CodeMap 仓库自身,437 符号 /
1232 边):

| Bench | 中位数 | 目标(设计文档 §21) |
|---|---:|---:|
| 全量索引 | 73 ms | ≤ 3 s |
| `callers` | 4.7 µs | ≤ 50 ms |
| `callees` | 26 µs | ≤ 50 ms |
| `walk_chain` depth 10 | 72 µs | ≤ 200 ms |

本地复现:`pytest -m bench -o addopts=""`。任一 PR 让中位数恶化 ≥
20% 都会被 CI 阻塞(ADR-010)。完整表格与方法论:
[`docs/performance.md`](docs/performance.md)。

---

## 文档

| 文件 | 主题 |
|---|---|
| [`docs/cli.md`](docs/cli.md) | 全部命令、选项、JSON envelope、退出码 |
| [`docs/configuration.md`](docs/configuration.md) | 所有配置键 + 合并顺序 |
| [`docs/plugin-guide.md`](docs/plugin-guide.md) | 如何写 indexer / bridge 插件 |
| [`docs/performance.md`](docs/performance.md) | 性能基线 + ADR-010 回归政策 |
| [`docs/indexers/python.md`](docs/indexers/python.md) | Python indexer 细节 |
| [`docs/bridges/http_route.md`](docs/bridges/http_route.md) | HTTP 路由桥接器契约 |
| [`docs/adr/`](docs/adr/) | 架构决策记录(1–12 + L001) |
| [`CHANGELOG.md`](CHANGELOG.md) | 发布记录 |

---

## 贡献

参见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。核心不变量:**任何语言都
不享有一等公民地位**。任何对某个生态做特殊化处理的提案,会被要求重构
为通用插件协议(ADR-L001)。

CI 对每个 PR 都强制 `ruff`、`mypy --strict`、`import-linter`、
`pytest --cov 80%`、以及 benchmark 套件。

---

## 许可证

MIT —— 详见 [`LICENSE`](LICENSE)。
