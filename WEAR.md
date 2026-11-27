# 专用版印量

发行台和压印台各用自己的库，继续按 README.md 的环回 JSON HTTP 约定办理。两台通过各自的业务接口核实正式记录。领班每次只管理一批、一块专用版，登记前须先建版号。该版可出现在未使用的固定稿中。已有纸单的原稿或其正式改稿候选能用到该版时，拒绝开批。开批后的普通纸单和普通改稿只使用普通版。批内纸自签发起沿用同一固定稿。

## 办理入口

使用 `POST /操作名`，成功仍用 `result` 包装。沿用 README.md 的标识、正整数与错误约定。下列字段名用于本地操作程序。

| 台别 | 操作 | 请求 | `result` 内容 |
| --- | --- | --- | --- |
| 发行 | `wear.open` | `batch`、`plate`、`total` | 同名三字段，`total` 为该版获准的实压次数 |
| 发行 | `wear.issue` | `batch`、`paper`、`edition`、`request_id` | `batch`、`paper`、`original`、`request_id`，其中 `original` 是签发采用的固定稿号 |
| 压印 | `wear.load` | `batch`、`paper`、`label`、`ticket_ids` | `batch`、`paper` 和按数字升序排列的 `ticket_ids` |
| 发行 | `wear.reconcile` | `batch`、`paper` | 核回后本批的 `batch`、`plate`、`total`、`used`、`held`、`free` |
| 发行 | `wear.balance` | `batch` | 同样六个字段，读取现账，可在压印台离线时查询 |

批号和参数相同可复领原开批结果。批内用原 `ticket` 预领所需的印票，位次及落位仍按固定备选办理。压印台联网时以 `wear.load` 验纸标签并装入一组正式票，然后沿原 `stage` 办理 `mount`。`label` 与纸号一致，`ticket_ids` 是一组不重复的正整数，至少含一张本纸原票。按原批、纸及同一组票可复领装入结果，调换票号排列仍是同一组。改组、混入别纸的票或批单身份不符均退回。准备完毕后，原 `press` 以原票号办理实际压印，已经装入的合法下一步在发行台离线时仍可办理。原入口同样执行专用版的批单和装入校验。已成立的原执继续由 `receipt`、`press` 和 `receive` 按原号核对和复领。

服务间另用两条内部路由核对原记录：发行端的 `wear.paper`（`batch`、`paper`，或仅 `paper`）回本批纸号、采用稿与请求号，压印台据此校验批单身份并区分是否批内纸；压印端的 `wear.state`（`batch`、`paper`）在一条事务里回该纸已登记的实压整步与是否已退台（含首次上台前退回），两者始终同刻读取，核回不会把某刻的印次与他刻的退台拼成一份可放量的事实。

`used` 是已核实的实耗，`held` 是各未退台纸单在已核实进度上相容备选的最大剩余耗用之和。`free` 等于 `total` 减去 `used` 与 `held`。新纸以空前缀计，余量足够就签发。`wear.reconcile` 向台端核实已发生的压印或退台。核实退台时本纸的最终实耗仍占印量，可释放本纸未用的保留量。压台暂时不可达时返回 503，保持现账。重复核回和同一授权的旧证迟到都返回现账，每份印量只释放一次。`wear.balance`、查执和核回均只查实作事实及办理账务。

余量不足、同一请求号改参、同一纸号另号再签及其他业务冲突返回 409，失败保持记录原样。成功签单以本批内的 `request_id` 复领，重开也返回原纸单。退台仍须有一条印序完整匹配，处在完整短序时也可沿相容长序继续压。成品按原 `release` 和 `pickup` 办理，保留实际印序中每笔的原票、原执和装台出处。旧接口和历史记录照 README.md 的约定继续办理。

## 两张纸共用 B

在空库用 `wear_fixture.seed_plates` 登记 A、B、C、D。初次 `wear.open` 请求示例为 `{"batch":"W","plate":"B","total":2}`。`wear_fixture.seed_editions` 登记三个固定稿，字母对应 README.md 的整步。`fork` 是 `[A,B,B]` 或 `[C,B]`，`one` 是 `[B]`，`edge` 是 `[C]` 或 `[C,B]`。

1. 发送 `wear.issue`，正文为 `{"batch":"W","paper":"P","edition":"fork","request_id":"sign-P"}`。预领 P 的首位 A、首位 C、次位 B 和第三位 B。将发行台实际返回的票号填入 `wear.load` 的 `ticket_ids`，另三项为 `{"batch":"W","paper":"P","label":"P"}`。装台后断开发行台，压首位 C 并丢失业务回包。重开后复领原首执，纸上仍只有一个 C。
2. 用 `one` 给 Q 申请签单。核回前 `used=0, held=2, free=0`，请求退回。发行台用 `{"batch":"W","paper":"P"}` 核回，得到 `used=0, held=1, free=1`。此时压印台再次离线，Q 的原申请可签，额外同稿 R 申请退回。重送核回及晚到的旧进度，余额仍为 0。
3. P 的长序旧票不能首压。P、Q 各实际压一次 B 后各自退台并交件。最终分别为 `[C,B]` 和 `[B]`，余量为 0。重开可按原号核对签单、实压和成品。
4. 另用总量为 1 的批和 `edge` 稿。C 后核回，仍须保留一次 B。直接退台并核回时 `used=0, held=0, free=1`。从一份独立初态走 C、B 后才退台，结果为 `used=1, held=0, free=0`。核回时读到压 B 前的印次也不能将其与压 B 后的退台混作一份可放量的事实。

## 演练

`python3 -B wear_fixture.py` 重跑未开批时的原流程，展示原回执和成品。`workshop(root)` 通过环回 HTTP 调用真实服务，使用 `issue_link` 或 `press_link` 的 `intercept` 可暂时控制请求。`offline` 在办理前返回不可用，`lose_reply` 让所选操作办完后以 503 模拟业务回包未取得。也可在钩子里暂存真实业务响应再迟交。`reopen()` 用原来两库重建服务对象。

把本页批次演练纳入 `.pointwise-runtime.json`。沿用其现有版本和运行方式，`verify` 继续执行完整原回归并核对批次结果，断言失败须非零退出。`demo` 要展示核回前后的签单变化、台端实压和重开查件。两项沿用清单的命令参数数组格式。

本工程以 `verify_wear.py` 作为 `verify`：先跑原 `check_project`（含 `tests/test_wear.py`），再逐一重放 `wear_fixture` 的五个场景（原流程、两纸共 B、edge 退回、edge 续压、开批与普通规则），任一断言失败即非零退出。`demo` 为 `wear_demo.py`：先重放原一天，再输出两纸共 B 批的核回前余额、核回前退回与核回后签 Q、台端实压序列、结算余额和重开查件，以及 edge 两条结局。
