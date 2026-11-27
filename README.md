# 榆纸社区凸印工坊

排版员把教具试样的版号、落位和备选印序录入工作稿。领班冻结稿件、发行纸单和预领印票。压印员核对实际来纸和上台任次，沿纸上已有印迹逐次办理。交件员收下核齐并退台的纸，按号交付成品及每一印的原出处。

## 运行

使用 Python 3.11 标准库。`python3 -B check_project.py` 运行完整回归，入口由平台提供。`python3 -B -m unittest discover -s tests -t .` 可直接发现同一测试包。`python3 -B day.py` 在临时目录启用两台环回 HTTP 服务，制作两张纸，重开后领取，并输出实际印序和出处。

手动启动时，在项目目录的两个终端依次运行下列命令。省去 `--sample` 可从空库开工。启用样例时先启动发行台，压印台从发行台取回样例来纸的正式纸单。重复启动或重复启用样例保留既有数据。

```text
python3 -B -m issue.service --db issue.sqlite --port 8701 --peer-port 8702 --sample
python3 -B -m press.service --db press.sqlite --port 8702 --peer-port 8701 --sample
```

## JSON HTTP

所有操作使用 `POST /操作名` 和 JSON 对象。成功响应为 `{"result":值}`。业务拒绝响应为 `{"error":{"code":错误码,"message":说明}}`。HTTP 400 表示输入无效，404 表示所需记录不存在，409 表示状态或身份冲突，503 表示暂无法与对端通信。进程只绑定 `127.0.0.1`，供工坊的本地操作程序调用。下表所列标识为非空且无首尾空白的字符串，`position` 和 `ticket_id` 为正整数。整步如 `{"plate":"A","placement":"top"}`。样例的 B、C、D 分别位于 `middle`、`bottom`、`corner`。

| 端口 | 操作 | 请求字段 | 成功结果 |
| --- | --- | --- | --- |
| 8701 | `plate` | `plate`、`name` | 已登记版号和名称 |
| 8701 | `layout` | `layout`、`placements`、`sequences` | 当前工作稿。落位表列出版号可使用的整步，印序是整步数组的数组 |
| 8701 | `layout.read` | `layout` | 当前工作稿 |
| 8701 | `freeze` | `layout`、`edition` | 由工作稿校验得出的独立固定稿 |
| 8701 | `edition` | `edition` | 固定稿的完整备选印序 |
| 8701 | `issue` | `paper`、`edition` | 确定原发行稿的纸单 |
| 8701 | `order` | `paper` | 纸单及原冻结稿完整内容 |
| 8701 | `ticket` | `paper`、`position`、`step` | 正式票号、纸号、位次、整步、出票稿和采用请求号 |
| 8701 | `receive` | `paper`、`ticket_id` | 从台端取得原回执并归档 |
| 8701 | `received` | `paper` | 发行侧已收到的回执，按实际位次排列 |
| 8701 | `amend` | `paper`、`original`、`candidate`、`request_id` | `adopted`（已采用）、`incompatible`（不可承接）或 `pending`（待查） |
| 8701 | `amend.status` | `paper`、`request_id` | 查原号，已知时含台端正式裁决 |
| 8702 | `stage` | `paper`、`action`，按动作补充下列字段 | 来纸、上台、退回或退台记录 |
| 8702 | `stage.status` | `paper` | 来纸、上台历史、退回和退台凭据 |
| 8702 | `press` | `paper`、`ticket_id` | 实压回执或已兑现原票的原回执 |
| 8702 | `receipt` | `paper`、`ticket_id` | 只查询原回执 |
| 8702 | `impressions` | `paper` | 已登记纸的有序实压记录 |
| 8702 | `release` | `paper` | 冻结成品，含 `piece_id`、最终 `edition`、印序及出处 |
| 8702 | `pickup` | `piece_id` | 原冻结内容，并记一次领取 |
| 8702 | `pickup.history` | `piece_id` | 按次序排列的领取凭据 |

`stage` 的 `arrive` 要求 `label` 与纸单纸号一致。`mount` 和 `unmount` 均要求 `mount_id`。`return` 仅用于首次上台前的来纸。服务间使用 `ticket.read`（`ticket_id`）、`amend.record`、`adopt` 和 `adopt.status`（后三个均为 `paper`、`request_id`）核对原记录。`adopt` 只办理发行端已有的正式改稿请求。

## 工坊口径

- 备选印序逐一核验。空工作稿、空备选、未知版号或未登记落位无法冻结。版号与落位按整步精确比较。冻结后编辑工作稿不会改动固定稿或正式纸单。
- 上台建立空实压前缀。任一固定备选中的未来步均可预领，首次实压按当前实际上台纸、采用稿和有序前缀核验。出错时不追加实压或成功回执；已实压原票可在改稿或退台后复领。
- 领班在回复已到达时可把回执交给 `receive` 归档。实际压印账独立于领班所见记录。改稿比较完整实际前缀，空前缀也可合法承接。结论未查实时暂停新出票。同号同参重提可续办，查单只读取已成立结论。不可承接时原稿可继续，退台后也不会重新采用稿件。
- 实际印序与任一完整备选相等时可收尾。在同一前缀同时匹配较长备选时，退台前仍可续压其合法下一步。签件要求核齐并退台。成品按实压顺序保留原票、原回执、落位和首次稿，后续领取读取原冻结内容。
