# CodeMap

[English](./README.md) · **简体中文**

> 面向 AI Agent 的语言中立代码索引 —— 不必全项目搜索即可精确导航。

CodeMap 为代码库构建一份**确定性**的、基于 AST 的索引,让 AI Agent
(Claude Code、Cursor、Codex 等)无需 grep 整个项目即可拿到调用链、
路由映射与跨文件关联。索引过程是静态的、快速的、可复现的 —— **索引
路径上不依赖任何 LLM**。

**状态**:0.1.0 稳定版。已发布到 PyPI,主包名 `codemap-core`,
另含 14 个 `codemap-<lang>` 语言插件。

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
pipx inject codemap codemap-typescript codemap-java codemap-go \
                    codemap-rust codemap-swift codemap-kotlin \
                    codemap-ruby codemap-php codemap-sql \
                    codemap-bash codemap-c codemap-cpp \
                    codemap-csharp codemap-scala
```

若主包是用 `pip` 装的:

```bash
pip install codemap-typescript codemap-java codemap-go codemap-rust \
            codemap-swift codemap-kotlin codemap-ruby codemap-php \
            codemap-sql codemap-bash codemap-c codemap-cpp \
            codemap-csharp codemap-scala
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
