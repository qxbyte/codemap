# CodeMap PyPI 发布 —— 待人工执行清单

> 本清单只列**云端/自动化做不了、必须由你本人完成**的步骤。
> 每一步都自带精确字段值与验证命令,做完后请在对应小节末尾补
> `✅ 完成于 YYYY-MM-DD`。
>
> 维护说明:云端 agent 已把所有「不需要 PyPI 限速窗口 / 不需要本机凭证 /
> 不需要 PyPI 网页」的任务做完(见下「已完成」),剩下三类卡点都在这份清单里。

---

## 0. 状态快照(核查于 2026-06-01)

### 已完成(无需人工)
- PR #4(bump a2)、PR #5(`publish.yml` 改用 `uv pip install` + bump **a3**)均已合并
- `main` 上 15 个 `pyproject.toml` 全部 = `0.1.0a3`
- tag `v0.1.0a2`、`v0.1.0a3` 均已推送
- **TestPyPI:15/15 全部 `0.1.0a3`,各 2 个文件(wheel + sdist)**
  → **Trusted Publishing 闭环已端到端验证成功**
- 无 open PR、无 open issue

### 生产 PyPI 现状
| 项目 | 状态 |
|---|---|
| codemap-core / codemap-bash / codemap-c / codemap-cpp | ✅ `0.1.0a1`,各 2 文件 |
| 其余 11 个(typescript / java / go / rust / swift / kotlin / ruby / php / sql / csharp / scala) | ❌ 不存在,卡在「新项目创建」限速 |

### `publish.yml` 路由规则(已验证)
- tag `v<X>.<Y>.<Z>(a\|b\|rc)<N>` → **TestPyPI**
- tag `v<X>.<Y>.<Z>` → **PyPI**(生产,真发版)
- Trusted Publishing,无 token;环境名:生产=`pypi`,预发=`testpypi`

---

## 任务 A — 配置 11 个 PyPI Pending Publisher(网页,无 API)

> 这一步与限速**互不影响**,现在就能做,且做完后将来 CI 打 release tag 时
> 能自动「占名 + 上传」一气呵成。

**入口**:<https://pypi.org/manage/account/publishing/> → 滚到底「Add a pending publisher」

**对下面 11 个 Project Name 各填一次,其余字段固定不变:**

| 字段 | 值 |
|---|---|
| Owner | `qxbyte` |
| Repository name | `codemap` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

11 个 Project Name:
```
codemap-typescript
codemap-java
codemap-go
codemap-rust
codemap-swift
codemap-kotlin
codemap-ruby
codemap-php
codemap-sql
codemap-csharp
codemap-scala
```

**验证**:页面出现 11 条 Pending 条目。

✅ 完成于 ______

---

## 任务 B — 等 PyPI「新项目创建」限速窗口清空

- 限速起点:`2026-05-30 23:25 CST`;经验估计需 7–14 天。
- 期间**不要**对 PyPI 做任何新项目 twine upload(可能延长窗口);TestPyPI 不受影响,可照常用。
- 到点后用**单个文件**探测一次(见任务 C),不要 15 个批量试探。

✅ 窗口开放确认于 ______

---

## 任务 C — 占满 PyPI 11 个新项目(二选一,需本机 `~/.pypirc` 或 CI)

> 目标:让生产 PyPI 上 15 个项目都存在。版本用 `0.1.0a1` 还是 `0.1.0a3` 皆可,
> 占名本身不挑版本;建议直接用当前 `main` 的 `0.1.0a3` 保持一致。

### 路径 A:本机 twine(快,每个文件各算 1 次创建配额)
```bash
# 先 build a3(本机)
.venv/bin/python -m build            # 主包
for d in plugins/codemap-*; do (cd "$d" && rm -rf dist && /path/to/build); done
# 探测单个新项目是否放行
.venv/bin/twine upload --repository pypi --non-interactive --skip-existing \
    plugins/codemap-csharp/dist/codemap_csharp-0.1.0a3-py3-none-any.whl
# 若成功(窗口已开),立刻把其余批量传完
.venv/bin/twine upload --repository pypi --non-interactive --skip-existing \
    dist/* plugins/*/dist/*
# 若 429,继续等任务 B
```

### 路径 B:CI 占名(需任务 A 完成)
- 只有 **release tag `vX.Y.Z`**(无 a/b/rc 后缀)才会路由到生产 PyPI。
- 因此「占名」与「真发版」可合并:直接走任务 D 的 `v0.1.0` tag,Pending Publisher
  会在首次上传时自动建项目 + 转 Trusted。**注意**:新项目创建仍受限速约束,
  限速没开时 CI 这一步同样会失败。

> 实务建议:**首占名走路径 A**(限速一开就抢),`v0.1.0` 真发版走 CI(路径 B / 任务 D)。

**验证**(公开 API,云端也能跑):
```bash
for n in codemap-core codemap-typescript codemap-java codemap-go codemap-rust \
         codemap-swift codemap-kotlin codemap-ruby codemap-php codemap-sql \
         codemap-bash codemap-c codemap-cpp codemap-csharp codemap-scala; do
  curl -sf "https://pypi.org/pypi/$n/json" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('  %s: %s, %d files'%(d['info']['name'],d['info']['version'],len(d['urls'])))" \
    2>/dev/null || echo "  $n: MISSING"
done
# 期望 15 行齐全
```

✅ 15/15 占名完成于 ______

---

## 任务 D — 正式发布 v0.1.0(限速清空 + 任务 A 完成后)

1. 开分支 bump 版本(`0.1.0a3` → `0.1.0`,15 个 `pyproject.toml`),整理 `CHANGELOG.md`
   的 `[Unreleased]` → `## [0.1.0] — 2026-XX-XX`。
   > 插件对主包的依赖 `codemap-core>=0.1.0a1,<0.2` **不要动**(下限已覆盖 0.1.0)。
2. PR → 等 6 个 test matrix CI 绿 → squash merge。
3. 打 tag 触发生产发布:
   ```bash
   git checkout main && git pull
   git tag v0.1.0 -m "First production release"
   git push origin v0.1.0
   ```
4. `publish-to-pypi` 自动走 **PyPI 分支**,15 个并行 build+upload。
   **前置**:任务 A 的 11 个 Pending Publisher 必须就位,否则 OIDC 拿到 token 后找不到 publisher。
5. 用任务 C 的验证脚本确认 15/15 = `0.1.0`。
6. `gh release create v0.1.0`(或网页)创建 GitHub Release,notes 取 CHANGELOG 的 0.1.0 段。

> 第 1 步的 CHANGELOG 整理、第 6 步 release notes 草稿,云端 agent 可代劳——需要时叫我。

✅ v0.1.0 发布于 ______

---

## 任务 E — 发版后收尾(任务 D 完成后)

- **README/INSTALL 改安装命令**(`README.md` / `README.zh-CN.md` / `INSTALL.md` / `INSTALL.zh-CN.md`):
  `pip install git+https://...` → `pip install codemap-core`;pipx:`pipx install codemap-core`,
  插件 `pipx inject codemap codemap-java ...`。CLI 命令名仍是 `codemap`。
  > 这几个文件的改动云端 agent 可代劳。
- **手工确认 Trusted Publisher 转正**:11 个项目首次上传后 Pending 应自动转 Trusted,
  逐个看 `https://pypi.org/manage/project/<name>/settings/publishing/`。
- **(可选)撤销 bootstrap token**:确认全走 Trusted Publishing 后,在
  <https://pypi.org/manage/account/token/> 撤销 `~/.pypirc` 里的整账号 token。

---

## 应急

- **限速 7–14 天还不开**:退一步只发 `codemap-core` 主包,插件先用
  `pip install "git+https://github.com/qxbyte/codemap.git#subdirectory=plugins/codemap-X"`;
  或联系 PyPI 支持 <https://pypi.org/help/#contact>。
- **OIDC 一直失败**:核对 publish.yml 的 `environment.name` 与 PyPI Publisher 配置一致;
  确认 Pending Publisher 的 owner/repo/workflow 三项严格匹配;必要时给
  `pypa/gh-action-pypi-publish` 加 `with: verbose: true`。
