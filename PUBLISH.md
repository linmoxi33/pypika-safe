# 开源发布材料 · pypika-safe

> 本文档是发布时可直接复制粘贴的文案包。仓库已发布在 `linmoxi33/pypika-safe`。
> 项目本体说明见 `README.md`，版本变更见 `RELEASE_NOTES.md`。

---

## 1. 仓库基础信息

| 字段 | 值 |
|---|---|
| 仓库名 | `pypika-safe` |
| 建议 owner | `linmoxi33` |
| 显示名 / Description | `PyPika fork with dialect-aware SQL literal escaping — fixes a MySQL/ClickHouse injection path, NULL comparisons, and bound-parameter typing. Drop-in API.` |
| 主页 | 上游仓库 `https://github.com/kayak/pypika` |
| 许可证 | Apache-2.0（继承，`LICENSE.txt` 与上游逐字节一致） |
| 语言 | Python |
| Topics | `sql` `query-builder` `pypika` `sql-injection` `mysql` `clickhouse` `postgresql` `security` `python` `escaping` |
| 首个 tag | `v0.51.1.post1` |
| Fork 声明 | README / NOTICE 均声明：fork 自 kayak/pypika 0.51.1，非官方，与 Kayak.com 无关联 |

### 建仓命令

```bash
# 在 pypika-safe 目录内
git init
git add -A
git commit -m "fix: dialect-aware literal escaping, NULL criteria, parameter typing

Fork of kayak/pypika 0.51.1 (Apache-2.0).

- escape string literals per dialect (backslash doubled on MySQL/ClickHouse)
- reject NUL bytes and bytes values instead of emitting broken literals
- render IS NULL / IS NOT NULL for comparisons against a null literal
- reject IN / NOT IN with a NULL member; render empty IN as 1=0 / 1=1
- pass Python values to drivers instead of pre-rendered SQL fragments
- add Field.like_literal() with the matching ESCAPE clause
- add assert_safe_identifiers() audit
- 76 new tests; 1099 upstream tests still pass"

git branch -M main
gh repo create linmoxi33/pypika-safe --public --source=. --remote=origin \
  --description "PyPika fork with dialect-aware SQL literal escaping — fixes a MySQL/ClickHouse injection path, NULL comparisons, and bound-parameter typing. Drop-in API."
git push -u origin main
git tag -a v0.51.1.post1 -m "Dialect-aware literal escaping"
git push origin v0.51.1.post1
```

### Topics 设置

```bash
gh repo edit linmoxi33/pypika-safe \
  --add-topic sql,query-builder,pypika,sql-injection,mysql,clickhouse,postgresql,security,python,escaping
```

---

## 2. GitHub Release（v0.51.1.post1）

**Title**：`v0.51.1.post1 — dialect-aware literal escaping`

**Body**：直接使用 `RELEASE_NOTES.md` 全文。

**附件**：`pypika-safe-0.51.1.post1.zip`（源码包）

---

## 3. 一句话简介（各平台复用）

> PyPika 把所有字符串字面量按同一套规则转义，在 MySQL / ClickHouse 上这是错的 —— 一个反斜杠就能让值逃出引号。`pypika-safe` 是它的 fork，只改值发射层：按方言转义、`== None` 生成 `IS NULL`、`IN` 不再吞 NULL、绑定参数传真值。API 不变。

英文版：

> PyPika escapes every string literal the same way for every database — which is wrong on MySQL and ClickHouse, where a backslash escapes the next character. `pypika-safe` forks it and fixes only the value-emission layer: dialect-aware escaping, `IS NULL` for `== None`, sane `IN` semantics, and parameters that carry real Python values. Same API.

---

## 4. 中文发布稿（掘金 / V2EX / 知乎 / 公众号）

### 标题备选

1. 我给 PyPika 提了个 issue 没人修，于是自己 fork 了一个：MySQL 上的 SQL 注入
2. 一个反斜杠就能注入：PyPika 的方言盲区，以及我怎么修的
3. pypika-safe：只改值发射层的 PyPika fork

### 正文

**先说结论**：PyPika 生成字符串字面量时，只做一件事 —— 把单引号翻倍。这在 PostgreSQL / SQLite 上是对的，在 MySQL / ClickHouse 上是错的，因为这两个库的反斜杠本身也是转义符。

于是这段代码：

```python
payload = "x\\' OR 1=1 -- "
MySQLQuery.from_(users).select(users.star).where(users.name == payload).get_sql()
```

生成的是：

```sql
SELECT * FROM `users` WHERE `name`='x\'' OR 1=1 -- '
```

反斜杠把 `'` 转义掉了，单引号翻倍反而白做，字面量提前闭合，`OR 1=1` 成了 SQL 的一部分。返回值是全表。

这是上游 issue #844，2025 年 7 月开的，到现在还开着。更早的 #238 是 2019 年开的。项目在慢速维护状态（#737 里维护者自己说的）。

**所以我 fork 了它，只改一件事：值怎么发射。**

修完之后：

```sql
SELECT * FROM `users` WHERE `name`='x\\'' OR 1=1 -- '
```

反斜杠先翻倍，引号再翻倍，字面量闭合不了。

顺手修了同一层的几个坑：

| 问题 | 原来 | 现在 |
|---|---|---|
| `field == None` | `= null`（永远匹配 0 行） | `IS NULL` |
| `isin([1, None])` | `IN (1,null)`（永远不成立） | 直接抛异常 |
| `isin([])` | `IN ()`（多数库语法错） | `1=0` |
| 绑定参数 | `["'foobar'"]`（带引号） | `["foobar"]` |
| `datetime.date` 参数 | `"'2024-02-22'"` 字符串 | `date(2024, 2, 22)` |
| `b"abc"` | 字面量 `b'abc'` | 抛 `UnsafeLiteralError` |

**验证方式**（这部分我觉得比结论重要）：

1. 测试套件：1099 条上游测试全过，新增 76 条。新测试断言的是"渲染出来的 SQL"和"真 SQLite 里查出来的行"，不是"函数存在"。
2. 差分对照：`tools/upstream_compare.py` 用同一份 15 条属性分别跑原库和 fork —— 原库 3 过 12 败，fork 15 全过。那 3 条过的是对照组，用来证明这个脚本不是"什么都能判失败"。
3. MySQL 语法往返：13 条注入形状的载荷，每条渲染后用 MySQL 语法解析回来，逐字节比对；再检查解析树里有没有多出 `OR` / `DROP` / `SELECT` 节点。原库 9/13，fork 13/13。
4. 严格引擎：DuckDB 拒绝 `IN ()`（SQLite 会容忍，所以 SQLite 证明不了这个修复有用）。

**没做到的也说清楚**：本机没有 MySQL / PostgreSQL / ClickHouse 服务，所以方言行为是靠语法往返和严格引擎验证的，不是连真库跑的。README 里明确写了这一条。

**许可证**：Apache-2.0，`LICENSE.txt` 与上游逐字节一致，`NOTICE` 列了原始版权（Kayak.com、Timothy Heys）、fork 版权和完整改动文件清单 —— Apache-2.0 第 4 条要求保留 NOTICE，这条不能省。

代码：`https://github.com/linmoxi33/pypika-safe`

---

## 5. 英文发布稿（Hacker News / Reddit r/Python / dev.to）

### Title

`Show HN: PyPika fork that fixes a MySQL SQL injection in literal escaping`

### Body

PyPika renders every string literal the same way regardless of database: it doubles the quote character and stops there. That is correct for PostgreSQL and SQLite. It is wrong for MySQL and ClickHouse, where a backslash also escapes the following character — so a value ending in `\` swallows the closing quote, and `\'` cancels out the doubling.

```python
payload = "x\\' OR 1=1 -- "
MySQLQuery.from_(users).select(users.star).where(users.name == payload).get_sql()

# upstream 0.51.1
# SELECT * FROM `users` WHERE `name`='x\'' OR 1=1 -- '     -> returns every row
# this fork
# SELECT * FROM `users` WHERE `name`='x\\'' OR 1=1 -- '    -> returns the literal
```

Upstream issue #844 has been open since July 2025; #238 since 2019. The maintainers describe the project as being in slow personal-maintenance mode (#737).

So I forked it and changed exactly one layer: how values are emitted. Same public API, same import name.

Along the way I fixed what else was broken in that layer:

- `field == None` emitted `= null`, which is valid SQL that matches nothing. Now `IS NULL`.
- `isin([1, None])` emitted `IN (1,null)`, which can never be true. Now raises.
- `isin([])` emitted `IN ()`, a syntax error on PostgreSQL / Oracle / MSSQL / DuckDB. Now `1=0`.
- Bound parameters stored pre-rendered SQL (`["'foobar'"]`, `"'2024-02-22'"`). Now they carry Python values.
- `b"abc"` leaked as the literal `b'abc'`. Now rejected.

How I verified it, because "I fixed a security bug" is cheap to claim:

1. **Test suite** — 1099 upstream tests still pass; 76 new ones. The new tests assert rendered SQL and rows from a real SQLite database, not the existence of functions.
2. **Differential harness** — `tools/upstream_compare.py` runs the same 15 properties against either checkout. Upstream: 3 pass, 12 fail. Fork: 15 pass. The 3 that pass upstream are controls, there to show the harness is not rigged.
3. **MySQL grammar round-trip** — 13 injection-shaped payloads rendered, parsed back with a MySQL grammar, compared byte-for-byte, plus a structural check for extra `OR` / `DROP` / `SELECT` nodes. Upstream 9/13, fork 13/13.
4. **Strict engine** — DuckDB rejects `IN ()` (SQLite tolerates it, so SQLite cannot prove that fix matters).

**What I did not do**: no MySQL / PostgreSQL / ClickHouse server was available here, so dialect behaviour is verified by grammar round-trip and strict-engine execution rather than a live server. That limitation is stated in the README rather than glossed over.

Apache-2.0, inherited. `LICENSE.txt` is byte-identical to upstream; `NOTICE` lists the original copyright, the fork copyright, and every modified file, as section 4 requires.

`https://github.com/linmoxi33/pypika-safe`

---

## 6. 上游反馈 Issue 草稿（可选，仅在你愿意时发）

> ⚠️ 发之前先确认：这是给上游的 bug report，不是广告。不要在里面贴 fork 链接当推广；如果维护者问起再提。

**Title**：`Literal escaping is dialect-blind: backslash escapes on MySQL/ClickHouse (#844 follow-up)`

**Body**：

```markdown
Following #844 and #238, I spent some time tracing this through `ValueWrapper`.

The root cause is that `format_quotes()` in `pypika/utils.py` only doubles the
quote character:

    def format_quotes(value, quote_char):
        if quote_char:
            value = str(value).replace(quote_char, quote_char * 2)
        return f"{quote_char}{value}{quote_char}"

That is correct for standard SQL. On MySQL and ClickHouse a backslash also escapes
the next character, so:

- `"a\\"` renders as `'a\'` — the trailing backslash escapes the closing quote and
  the literal is unterminated;
- `"x\\' OR 1=1 -- "` renders as `'x\'' OR 1=1 -- '` — the backslash escapes the
  first of the doubled quotes, the literal closes, and `OR 1=1` becomes SQL.

`QueryBuilder` already knows its dialect (`self.dialect`), and it is already passed
through kwargs as `dialect=`, so `ValueWrapper.get_formatted_value` has everything it
needs to branch on `Dialects.MYSQL` / `Dialects.CLICKHOUSE`.

I worked around it in a fork (happy to send a patch instead if that is more useful).
The escaping I ended up with doubles the backslash before doubling the quote, which
keeps the output parseable under both `sql_mode` settings:

    "'x\\\\'' OR 1=1 -- '"

Two related things I noticed in the same code path, in case they are useful:

1. `ValueWrapper.get_sql(parameter=...)` stores `get_value_sql(...)` as the parameter
   value, so drivers receive `"'foobar'"` (with quotes) and dates arrive as
   `"'2024-02-22'"`.
2. `field == None` renders `= null`, which is valid SQL that matches no rows.

I have a 15-property comparison script that runs against any checkout if you want to
see the full list; it reports 3 pass / 12 fail on 0.51.1.
```

---

## 7. 发布检查清单

- [ ] `git log` 无敏感信息（token / 本机路径 / 用户名）
- [ ] `LICENSE.txt` 与上游逐字节一致（`sha256sum` 对比）
- [ ] `NOTICE` 包含原始版权 + fork 版权 + 改动文件清单
- [ ] README 首屏写明 fork 自哪个版本、非官方
- [ ] 测试可复现：干净环境 `pip install -r requirements-dev.txt` 后四条命令全绿
- [ ] Release 附件里的 ZIP 与 tag 内容一致
- [ ] 不在上游 issue 里做 fork 推广
