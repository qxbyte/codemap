# 安装指南

[English](./INSTALL.md) · **简体中文**

> **0.1.0**(2026-06-03)起,CodeMap 已发布到 PyPI,主包名
> `codemap-core`,另含 14 个 `codemap-<lang>` 语言插件。下面命令默认
> 以 PyPI 为安装来源;[从 git 安装](#28-从-git-安装跟随-main--锁定-commit)
> 一节保留旧的 `git+https://…` 方式,适合需要跟 `main` 或锁定
> commit 的用户。文末 [验证日志](#7-验证日志) 是 2026-05-30 那次
> [`qxbyte/codemap@c4cd436`](https://github.com/qxbyte/codemap/commit/c4cd436)
> pre-release 验证的逐字记录,命令与数字均真实,但里面用的是旧的
> `git+https://…` 安装 URL。

---

## 目录

- [TL;DR](#tldr)
- [1. 系统要求](#1-系统要求)
- [2. 安装主 CLI](#2-安装主-cli)
  - [2.8 从 git 安装](#28-从-git-安装跟随-main--锁定-commit)
- [3. 验证](#3-验证)
- [4. 安装语言插件](#4-安装语言插件)
  - [4.6 从 git 安装](#46-从-git-安装跟随-main--锁定-commit)
- [5. 第一次使用](#5-第一次使用)
- [6. 升级与卸载](#6-升级与卸载)
- [7. 验证日志](#7-验证日志)
- [8. 离线分发](#8-离线分发)
- [9. 常见问题](#9-常见问题)

---

## TL;DR

```bash
# 1. 装 pipx(一次性,系统级)
brew install pipx && pipx ensurepath          # macOS
# 或 Linux:  python3 -m pip install --user pipx && pipx ensurepath

# 2. 装主 CLI(从 PyPI)
pipx install codemap-core

# 3. 按需注入语言插件
pipx inject codemap codemap-java

# 4. 开干
cd ~/your-project
codemap index .
codemap doctor
codemap routes
```

完事。下面只是把这 4 步展开,并给出几种等价的替代方案。

---

## 1. 系统要求

| 项 | 要求 | 说明 |
|---|---|---|
| Python | **≥ 3.11** | 开发用 3.13。macOS 系统自带的 `python3` 通常是 3.9,先装新版。 |
| OS | macOS / Linux | Windows 可索引,但 `--watch` 会降级为轮询。 |
| 网络 | **仅安装时**需要 | 拉仓库 + 下 `tree-sitter-*` 二进制 wheel。索引阶段全离线。 |
| 磁盘 | 主 CLI ~30 MB,每个语言插件 ~1–5 MB | 可忽略。 |

先查 Python 版本:

```bash
python3 --version
# 如果低于 3.11,先升级:
#   macOS:  brew install python@3.12
#   Linux:  apt install python3.12  (或对应包管理器)
#   跨平台:  pyenv install 3.12.7 / uv python install 3.12
```

---

## 2. 安装主 CLI

CodeMap 在 PyPI 上的发行名是 `codemap-core`。三种装法任选:

### 2.1 用 `pipx`(推荐)

`pipx` 把每个工具隔离在独立 virtualenv,并把 `codemap` 命令放进 `$PATH`
—— 这正是 CLI 工具该有的形态。

```bash
pipx install codemap-core
```

### 2.2 用 `uv tool`

隔离模型同 pipx,但更快:

```bash
uv tool install codemap-core
```

### 2.3 用普通 `pip`(不推荐)

会污染当前激活的环境。只在你完全掌控的 virtualenv 里用:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install codemap-core
```

### 2.4 可选 extras

```bash
# `codemap index --watch` 需要 watchdog
pipx install "codemap-core[watch]"

# 开发工具集(pytest、ruff、mypy、import-linter、pytest-benchmark)
pipx install "codemap-core[dev]"
```

### 2.5 锁定到具体版本

```bash
pipx install "codemap-core==0.1.0"
```

### 2.6 预发布版本(alpha / beta / rc)

`pipx` 默认跳过预发布,加 `--pip-args="--pre"` 才会装:

```bash
pipx install --pip-args="--pre" codemap-core
```

### 2.7 升级

```bash
pipx upgrade codemap                  # 主包升级,已注入的插件自动跟随
uv tool upgrade codemap               # uv 等价
pip install --upgrade codemap-core    # venv 内的 pip
```

### 2.8 从 git 安装(跟随 main / 锁定 commit)

如果想用 `main` 上未发布的改动,或者要锁到具体 commit,git URL
形式仍可用:

```bash
# 跟随 main
pipx install git+https://github.com/qxbyte/codemap.git
pip install git+https://github.com/qxbyte/codemap.git

# 锁定 commit
pipx install "git+https://github.com/qxbyte/codemap.git@<commit-sha>"

# 带 extras
pipx install "git+https://github.com/qxbyte/codemap.git#egg=codemap[watch]"
```

---

## 3. 验证

```bash
codemap --version
# → 0.1.0

codemap --help        # 全局选项 + 子命令列表

cd /tmp/empty-dir     # 任何没有 .codemap/ 的空目录
codemap doctor
```

干净安装(还没装语言插件)应看到 **2 个 indexer + 2 个 bridge**:

```
                  Registered indexers
┃ name          ┃ version ┃ languages ┃ file_patterns ┃
│ _example_lang │ 0.1.0   │ example   │ *.example     │
│ python        │ 0.1.0   │ python    │ *.py, *.pyi   │

             Registered bridges
┃ name                ┃ version ┃ requires ┃
│ http_route          │ 0.1.0   │ -        │
│ python_cross_module │ 0.1.0   │ -        │
```

> `_example_lang` 是给插件作者看的参考实现,负责解析 `*.example` 文件,
> 主要用来保证插件契约正确。实际使用时可以无视它。

---

## 4. 安装语言插件

每个非 Python 语言的 indexer 都作为**独立 PyPI 包**放在 `plugins/`。
装上一个就多一种语言;通过 `entry_points` 自动发现,**不需要改任何
配置**。

### 4.1 可用插件清单

| 语言 | 子目录 | 文件模式 | 底层 grammar |
|---|---|---|---|
| TypeScript / TSX | `plugins/codemap-typescript` | `*.ts`, `*.tsx` | `tree-sitter-typescript` |
| Java | `plugins/codemap-java` | `*.java` | `tree-sitter-java` |
| Go | `plugins/codemap-go` | `*.go` | `tree-sitter-go` |
| Rust | `plugins/codemap-rust` | `*.rs` | `tree-sitter-rust` |
| Swift | `plugins/codemap-swift` | `*.swift` | `tree-sitter-swift` |
| Kotlin | `plugins/codemap-kotlin` | `*.kt`, `*.kts` | `tree-sitter-kotlin` |
| Ruby | `plugins/codemap-ruby` | `*.rb` | `tree-sitter-ruby` |
| PHP | `plugins/codemap-php` | `*.php` | `tree-sitter-php` |
| SQL(仅 DDL) | `plugins/codemap-sql` | `*.sql`, `*.ddl` | `tree-sitter-sql` |
| Bash | `plugins/codemap-bash` | `*.sh`, `*.bash`, `*.bats` | `tree-sitter-bash` |
| C | `plugins/codemap-c` | `*.c`, `*.h` | `tree-sitter-c` |
| C++ | `plugins/codemap-cpp` | `*.cpp`, `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.hxx` | `tree-sitter-cpp` |
| C# | `plugins/codemap-csharp` | `*.cs`, `*.csx` | `tree-sitter-c-sharp` |
| Scala | `plugins/codemap-scala` | `*.scala`, `*.sc` | `tree-sitter-scala` |

### 4.2 用 `pipx inject`(推荐)

`pipx inject` 把插件装进主 CLI 所在的隔离环境:

```bash
# 17 个语言一次性装齐
pipx inject codemap codemap-typescript codemap-javascript codemap-vue \
                    codemap-java codemap-jsp codemap-go \
                    codemap-rust codemap-swift codemap-kotlin \
                    codemap-ruby codemap-php codemap-sql \
                    codemap-bash codemap-c codemap-cpp \
                    codemap-csharp codemap-scala

# 或单个装
pipx inject codemap codemap-typescript
```

### 4.3 用 `uv tool inject`

```bash
uv tool inject codemap codemap-java
```

### 4.4 用普通 `pip`

如果你是 `pip` 装在激活的 virtualenv 里,插件也用同样方式:

```bash
pip install codemap-java
```

### 4.6 从 git 安装(跟随 main / 锁定 commit)

要用 `main` 上未发布的插件或锁定 commit,用子目录 URL:

```bash
pipx inject codemap "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
```

### 4.5 验证插件已注册

```bash
codemap doctor
```

每装一个插件,**Registered indexers** 表里就会立刻多一行,无需任何额外
配置。如果没出现,跳到 [常见问题](#9-常见问题)。

### 4.7 AI-Enterprise-Delivery-System 工作流插件(可选)

codemap 是四层记忆模型工作流的**代码侧**那一半。**spec / 执行 /
知识沉淀**那一半在另一个插件家族
[`pluginhub`](https://github.com/qxbyte/pluginhub)。它们完全可选——
codemap 本身可独立跑——但如果想要完整闭环,就装上:

```
新需求进入
   ↓ specode → requirements / design / execute / acceptance
   ↓ task-swarm(多 agent 并发执行)
   ↓ specode-distill(知识写到 <project_root>/.ai-memory/knowledge/ + knowledge-base/)
   ↓ 下一个需求 → codemap recall 拉历史知识 → 注入新 spec
```

三个 pluginhub 插件通过 AI IDE 自己的 plugin manager 安装(以 Claude
Code 为例;Codex / Copilot CLI 同理):

```
# 在 Claude Code 内
/plugin marketplace add github:qxbyte/pluginhub
/plugin install specode      # spec 工作流 + 内置 specode-distill 子 skill
/plugin install task-swarm   # 多 agent pipeline 编排

# 可选:superpowers — brainstorming / writing-plans / TDD 套件;specode 优先调用
/plugin marketplace add github:obra/superpowers-marketplace
/plugin install superpowers
```

| 插件 | 最低版本 | 写入 `<project_root>/` | 触发时机 |
|---|---|---|---|
| `specode` | **3.0.0** | (仅通过下面的 specode-distill 子 skill) | 驱动 spec 全生命周期 |
| └─ `specode-distill` | (specode 3.0 子 skill) | `.ai-memory/knowledge/{rules,business,modules,cases,pitfalls}/*.yml` + `knowledge-base/*.md`(双产) | 用户 `/specode:specode-distill <slug>`,或 specode acceptance 末尾选"是" |
| `task-swarm` | **0.6.0** | `.ai-memory/knowledge/{cases,pitfalls}/*.yml` + `knowledge-base/*.md`(双产) | 每次 `task_swarm.py resolve` 成功收尾时自动 |
| `superpowers` | 任意 | — (不写 `.ai-memory/`) | specode 调它的 brainstorming / writing-plans 等 skill |

装完后新增的 slash command:

| 插件 | 命令 |
|---|---|
| specode | `/specode:specode-spec`, `/specode:specode-continue`, `/specode:specode-list`, `/specode:specode-distill` |
| task-swarm | `/task-swarm:swarm` |

specode 2.1+ 在 requirements phase 自动调 **`codemap recall`**(来自
`codemap-aimemory` PyPI 包),在写新 spec 前拉历史知识。所以想要完整
集成时:

```bash
# 确保 codemap-aimemory 装了(它带 `codemap recall`)
pipx inject codemap codemap-aimemory   # 如果 §4.2 还没装

# 验证 recall 可用
codemap recall --help                  # 应打印用法
```

没装 `codemap-aimemory` 时,spec 工作流仍能跑——specode 的 context-recall
那一步就静默 no-op。

pluginhub 插件家族还有独立的 Obsidian-vault 维护工具线(`obsidian-wiki`
2.0+)。**不是** AI-EDS 工作流的一部分——只在你同时也想维护一个
Obsidian LLM-wiki 时单独装。

---

## 5. 第一次使用

```bash
cd /path/to/your-project

# 建立索引(产物写到 ./.codemap/)
codemap index .

# 看一下索引健康度
codemap doctor                        # 插件 + 索引状态
codemap diagnostics --severity error  # 解析器报错/警告(如有)

# 查询
codemap search login -n 5
codemap get '<symbol-id>'             # 单个符号的源码片段
codemap callers '<symbol-id>'         # 谁调用了它
codemap callees '<symbol-id>'         # 它调用了谁
codemap trace --from '<id>' --depth 5
codemap routes                        # http_route bridge 找到的所有 HTTP 路由

# 知识检索(需要 codemap-aimemory 插件,0.3.5+)
# 扫 .ai-memory/knowledge/*.yml——如果你装了 pluginhub 工作流
# (见 §4.7),specode-distill / task-swarm 会写这些 yml。
codemap recall '<query>'              # 默认 top-k 5,yaml
codemap recall '<query>' -k 10 -o json
codemap recall '<query>' -t rules,pitfalls

# 喂给 AI agent 的结构化输出
codemap --json routes
codemap --json callers '<symbol-id>'
```

后续重建:

```bash
codemap index . --incremental         # 只重解析 sha256 变了的文件
codemap index . --watch               # 后台常驻(需要 [watch] extra)
codemap index . --rebuild             # 全部丢弃从头重建
codemap index . --dry-run             # 只报会做什么,不写盘
```

配置文件:`.codemap/config.yaml`(项目级)+
`~/.config/codemap/config.yaml`(用户级)。完整字段见
[`docs/configuration.md`](docs/configuration.md)。

---

## 6. 升级与卸载

### 升级

```bash
pipx upgrade codemap                  # 拉最新 main;注入的插件一并跟随
uv tool upgrade codemap               # uv 等价命令
```

升级到指定 commit:

```bash
pipx uninstall codemap
pipx install "git+https://github.com/qxbyte/codemap.git@<commit-sha>"
# 然后重新 inject 你要的插件
```

### 卸载

```bash
pipx uninstall codemap                # CLI 和所有注入的插件一并清掉
uv tool uninstall codemap             # uv 等价命令
```

各项目里的 `.codemap/` 目录是独立的 —— 想让某个项目"失忆",手动删它就行。

---

## 7. 验证日志

下面是 **2026-05-30** 在干净 venv 里跑出来的逐字记录,目标版本是
[`qxbyte/codemap@c4cd436`](https://github.com/qxbyte/codemap/commit/c4cd436)。
每个数字和表格都是命令真实输出。

### 7.1 环境

```bash
$ python3.12 -m venv /tmp/codemap-fresh
$ /tmp/codemap-fresh/bin/python --version
Python 3.12.13
```

### 7.2 装主 CLI(≈ 2 分钟)

```bash
$ time /tmp/codemap-fresh/bin/pip install "git+https://github.com/qxbyte/codemap.git"
...
Successfully installed annotated-doc-0.0.4 annotated-types-0.7.0
  codemap-0.1.0 markdown-it-py-4.2.0 mdurl-0.1.2 pydantic-2.13.4
  pydantic-core-2.46.4 pygments-2.20.0 pyyaml-6.0.3 rich-15.0.0
  shellingham-1.5.4 typer-0.26.3 typing-extensions-4.15.0
  typing-inspection-0.4.2

pip install  2.36s user  1.00s system  2% cpu  2:05.55 total
```

### 7.3 验证(秒级)

```bash
$ /tmp/codemap-fresh/bin/codemap --version
0.1.0

$ cd /tmp/codemap-demo-project   # 空目录
$ /tmp/codemap-fresh/bin/codemap doctor
CodeMap 0.1.0
project_root: /private/tmp/codemap-demo-project

                  Registered indexers
┃ name          ┃ version ┃ languages ┃ file_patterns ┃
│ _example_lang │ 0.1.0   │ example   │ *.example     │
│ python        │ 0.1.0   │ python    │ *.py, *.pyi   │

             Registered bridges
┃ name                ┃ version ┃ requires ┃
│ http_route          │ 0.1.0   │ -        │
│ python_cross_module │ 0.1.0   │ -        │

No `.codemap/` directory found. Run `codemap index` to build one.
```

### 7.4 注入语言插件(≈ 16 秒)

```bash
$ time /tmp/codemap-fresh/bin/pip install \
    "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java"
...
Successfully installed codemap-java-0.1.0 tree-sitter-0.25.2 tree-sitter-java-0.23.5

pip install  0.75s user  0.41s system  7% cpu  15.608 total
```

```bash
$ /tmp/codemap-fresh/bin/codemap doctor | head -10
                  Registered indexers
┃ name          ┃ version ┃ languages ┃ file_patterns ┃
│ java          │ 0.1.0   │ java      │ *.java        │   ← 自动发现
│ _example_lang │ 0.1.0   │ example   │ *.example     │
│ python        │ 0.1.0   │ python    │ *.py, *.pyi   │
```

### 7.5 索引一个 Java + Python 混合项目

fixture:一个 `User.java`(有 `greet()` 方法的类)+ 一个 `app.py`
(用 `@app.route("/users/<int:uid>")` 的 Flask 应用):

```bash
$ /tmp/codemap-fresh/bin/codemap index .
Indexed 2 files
┃ metric        ┃ count ┃
│ files_scanned │ 2     │
│ files_indexed │ 2     │
│ symbols       │ 6     │
│ edges         │ 1     │
│ routes        │ 1     │
│ diagnostics   │ 0     │
│ bridges_run   │ 2     │
```

搜索 + 路由查询:

```bash
$ /tmp/codemap-fresh/bin/codemap search greet
┃ kind   ┃ location    ┃ symbol         ┃
│ method │ User.java:5 │ String greet() │

$ /tmp/codemap-fresh/bin/codemap routes
┃ method ┃ path             ┃ handler  ┃
│ GET    │ /users/<int:uid> │ app.py:5 │
```

JSON 模式:

```bash
$ /tmp/codemap-fresh/bin/codemap --json routes
{
  "schema_version": "1.0.0",
  "command": "routes",
  "result": {
    "method_filter": null,
    "results": [
      {
        "method": "GET",
        "path": "/users/<int:uid>",
        "route_id": "scip-route . . . api/GET#`/users/<int:uid>`.",
        "handlers": [
          { "id": "scip-python . . . app.py/get_user().",
            "kind": "function", "language": "python",
            "file": "app.py", "line": 5 }
        ]
      }
    ]
  }
}
```

### 7.6 这次验证证明了什么

- 主 CLI **不内置任何语言偏好** —— 只有 `python` 和参考实现
  `_example_lang`,其它一切都按需通过插件加载。
- 插件**零配置**:`pip install` 一行,无需注册、无需改配置。
- `http_route` bridge **第一次索引就跨语言工作** —— Python 的 Flask 装饰
  器变成了 `scip-route` 符号,任何语言的 caller(比如假想的 Java 客户端)
  都能用同样的 SymbolID 格式连过来。
- `--json` 输出格式稳定,可以直接喂给 AI agent。

---

## 8. 离线分发

目标机器装的时候没网?在有网的机器上打 wheel 包:

```bash
# 在有网的机器上
mkdir codemap-offline && cd codemap-offline
pip download \
    "git+https://github.com/qxbyte/codemap.git" \
    "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-java" \
    "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-typescript" \
    -d ./wheels

# 打 tar 包,拷到目标机器
tar czf codemap-offline.tar.gz wheels/

# 在目标机器上
tar xzf codemap-offline.tar.gz
python3.12 -m venv /opt/codemap
/opt/codemap/bin/pip install --no-index --find-links=./wheels codemap codemap-java codemap-typescript
ln -sf /opt/codemap/bin/codemap /usr/local/bin/codemap
```

`pip download` 会解析整条依赖链并下载所有传递依赖的 wheel,包括平台相关
的 `tree-sitter-*` 二进制。两端**必须使用相同的 Python 大小版本号 +
相同的 OS/CPU 架构**。

---

## 9. 常见问题

### "python3 --version 显示 3.9.x"

macOS 自带的是老 Python。装个新版本然后显式用它:

```bash
brew install python@3.12
python3.12 -m venv .venv      # 直接用它
# 或者用 pyenv / uv / mise 管多版本
```

### "command not found: codemap"

`pipx install` 完成后跑一次 `pipx ensurepath` 并**开个新 shell**,让
`$PATH` 更新生效。验证位置:

```bash
pipx list                     # 查看所有装好的 app 及其路径
ls ~/.local/bin/codemap       # pipx 创建的符号链接
```

### "插件装了但 `doctor` 看不到"

插件必须装进**和主 CLI 同一个环境**。

- `pipx`:必须用 `pipx inject codemap <plugin>` —— **不能**在普通 shell
  里 `pip install`(那会装到完全不同的环境)。
- `uv tool`:用 `uv tool inject codemap <plugin>`。
- virtualenv:先 `source .venv/bin/activate` 再 `pip install`。

确认 CLI 用的是哪个 Python:

```bash
which codemap
head -1 $(which codemap)      # shebang 指向真正的 Python 解释器
```

### "安装时间 > 2 分钟 / 超时"

从 GitHub `pip install` 需要 clone 仓库(≈ 5 MB),首次还可能源码编译
`tree-sitter-*`。第二次以后走 wheel 缓存,秒级。

网络特别差的话,在有网机器上 `pip wheel` 出来复用(见
[离线分发](#8-离线分发))。

### "`doctor` 显示的 `.codemap/` 不是当前项目的"

CodeMap 会沿当前目录向上寻找最近的 `.codemap/` 作为 project root。
要么 `cd` 到目标项目根再跑,要么传绝对路径:

```bash
codemap index /path/to/project
```

### "tree-sitter-X 第一次装编译失败"

Apple Silicon 上有些 grammar(尤其是 `tree-sitter-rust`、
`tree-sitter-cpp`)编译要 30 秒 ~ 1 分钟,需要 Xcode 命令行工具:

```bash
xcode-select --install
```

Linux 上可能需要 C 编译器 + Python 开发头文件:

```bash
sudo apt install build-essential python3-dev          # Debian/Ubuntu
sudo dnf install gcc python3-devel                    # Fedora
```

### "只想卸某个语言插件,不想卸主 CLI"

```bash
pipx runpip codemap uninstall codemap-java            # pipx
uv tool uninstall-from codemap codemap-java           # uv
pip uninstall codemap-java                            # 普通 pip
```

然后 `codemap doctor` 确认它消失了。

---

如果还是不行,请在 <https://github.com/qxbyte/codemap/issues> 开 issue,
附上 `codemap doctor` 的完整输出和你用的安装命令。
