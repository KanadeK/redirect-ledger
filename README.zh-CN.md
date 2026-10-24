# Redirect Ledger 中文说明

迁移网站前，在本地检查 `source,target,status` CSV：找出重定向环路、重复来源、长链、缺失终点，以及同时被声明为页面和重定向的路径。配合新站路径清单使用，不需要服务器或网络。

Python 3.11+，运行时零第三方依赖，MIT。完整输入契约见 [英文 README](README.md)。

```sh
git clone https://github.com/KanadeK/redirect-ledger.git
cd redirect-ledger
python -m venv .venv
# 按当前 shell 的标准方式激活 .venv。
python -m pip install .
redirect-ledger examples/redirects.csv --inventory examples/live-paths.txt
redirect-ledger examples/redirects.csv --inventory examples/live-paths.txt --plan flattened.csv
redirect-ledger flattened.csv --inventory examples/live-paths.txt --strict
```

示例首先报告4条规则、0个错误、1个链式警告。生成的完整CSV只压缩全链同为301或同为308的永久重定向；混合状态和临时重定向保留原目标。文件已存在或审计有错误时拒绝写入。

路径精确匹配并区分大小写和尾斜杠。首版不支持query、fragment、正则、通配符、重写或平台规则优先级；编码歧义会报错。绝对HTTP(S)目标始终视作外部终点，不抓取、不声称验证了其存在。若为同站地址，先转换为根路径才能纳入图分析。

退出码0表示符合当前门禁；1为审计错误或启用 `--strict` 后出现警告；2为输入、文件或计划写入错误。使用 `--format json` 获取逐规则证据。报告会包含URL路径，分享前请审阅。

每个输入最多16 MiB、10万条规则或路径，路径最长4096字符。输入文件不会修改；可选计划写入新文件，但不保证断电时写入原子性。路径清单仅代表你声明的新站页面，部署后仍应检查真实HTTP响应。

卸载：`python -m pip uninstall redirect-ledger`；删除示例生成的 `flattened.csv`；按需停用并移除专用 `.venv`。程序没有后台服务或持久缓存。
