# FOMO 打狗策略纸面模拟系统

把打狗策略变成 24 小时纸面模拟程序, 附实时策略状态看板；本部署不执行实盘交易。

## 先说清楚三件事

1. **这不是"套利"**。Polymarket 那个 YES+NO=$1 是真套利; 打狗策略是趋势跟随+纪律止盈,
   名字里不写"套利"是为了不骗你。它的价值是纪律, 不是印钞。
2. **为什么绕过 fomo.family App**: fomo 官方没有公开 API, 用浏览器自动化会被封号
   (已有开源项目因此被封)。但 fomo 上的每笔交易都是 Solana 链上真实 swap,
   本系统直接在链上按代币 mint 跟踪你的仓位——你在 fomo 上买的币, 这里照样管得住。
   代价是: 仓位需要你手动录入(或看板表单添加), 因为 fomo 不开放读取持仓的接口。
3. **神经网络看板是系统状态的可视化, 不是预测**。输入层=持仓实时倍数,
   隐藏层=4 条策略规则(越接近触发越亮), 输出层=盈亏。它不预测行情,
   也不会让收益"稳定上涨"——meme 币没有稳定这回事, 保命靠的是止损规则和仓位。

## 策略 (占原始仓位)

- 规则1: 涨到 2x → 卖出 50%
- 规则4: 涨到 3x → 卖出 30% (剩下 20% 博高倍)
- 规则2: 跌到 0.5x → 全清 (最高优先级)
- 规则3: 到过 3x 后, 从峰值回撤 35% → 清仓

## 安装运行

```bash
cd fomo-dagou
pip install -r requirements.txt

python run.py check       # 单次检查 (只读)
python run.py paper       # 纸面执行循环 (默认)
python run.py paper-auto  # 纸面自动发现 + 带认证看板 (同一进程)
python run.py dashboard   # 仅看板/价格循环
python daily_report.py    # 输出最近24小时纸面实验日报
```

## 自动发现模式 (paper-auto, 实验)

`python run.py paper-auto` 启动后, 系统每 15 分钟扫描一次 DexScreener 热门榜:

1. 取 Solana 热门助推币, 拉取 pair 详情
2. 过滤: 流动性≥$5000、24h买卖盘活跃(有卖盘)、池龄<7天
3. RugCheck 安全检查: danger 或查不到 -> 直接跳过
4. **持仓集中度**: 前10持仓(排除LP池)≤30%, 超过直接跳过 —— 筛的是"筹码分散",
   不是"有价值", 有没有真实产品机器判断不了
5. 按流动性取前 **5** 个, 每个纸面买入 $10(虚拟), 最多同时持有5个自动仓
6. 买入后沿用同样的4条打狗规则管理卖出

虚拟本金 $100, 在看板"虚拟资金"卡片里实时看盈亏。**这只是实验, 不花真钱,
也不产生真收益** —— 跑两周看的是"策略+选币"有没有统计上的边际, 不是印钞。

硬边界 (写死在此部署代码里):
- 自动买入只做纸面记账，不会进入实盘或发起链上交易。
- 此部署不包含实盘执行器，不读取钱包私钥；`DOG_MODE` 等环境变量不能打开实盘路径。

加仓位: 打开看板 → 底部表单填 mint/简称/买入价(空=现价)/数量。
或直接编辑 positions.json。仓位状态保存在 state.json, 重启不丢失。

环境变量: `POLL_SEC`(默认20秒轮询)、`SLIPPAGE_BPS`(默认100=1%)、
`R1_MULT/R1_PCT/R4_MULT/R4_PCT/STOP_MULT/TRAIL_START/TRAIL_RETRACE` 均可调。
急停: `touch /tmp/dog_kill`。

## 交给 Cue 自动跑

1. 把 `fomo-dagou/` 整个文件夹发给你的 Cue agent
2. 让它 `pip install -r requirements.txt`, 先 `python run.py check` 确认能读到价格
3. 然后 `python run.py dashboard`, 把看板链接给你
4. 让它保持运行、每天汇报执行记录
5. 加仓时你直接在看板表单里加, 或让 Cue 帮你加

## 部署安全边界

此部署为纸面专用构建：实盘执行器已从部署目录移除，程序不读取私钥，
`DOG_MODE=live` 等环境变量也不会打开实盘路径。纸面自动买入与卖出只更新本地虚拟状态，
不会创建、签名或广播链上交易。看板启用 HTTP Basic Auth；不要公开分享认证密码。

## 诚实声明

- 纸面赚钱 ≠ 实盘赚钱; meme 币滑点、rug、流动性枯竭在纸面里都是打折的。
- 先纸面跑至少两周, 看执行记录是否符合预期, 再考虑实盘和仓位大小。
- 信息整理与代码学习用途, 不是投资建议; 实盘盈亏自负。


## Render 持久托管（纸面看板）

项目根目录的 `render.yaml` 是 Render Blueprint：启动 `python run.py paper-auto`，绑定 Render 提供的 `PORT`，将纸面状态写入持久盘 `/var/data/state.json`，并通过 `/healthz` 提供不含账户数据的健康检查。服务只做纸面模拟：虚拟本金 $100、每笔 $10、最多 5 个自动仓、每 15 分钟扫描一次；不会创建、签名或广播链上交易，也不读取钱包私钥。看板及所有业务 API 继续使用 HTTP Basic Auth；Render 上必须在 Blueprint 同步时安全填写 `DASHBOARD_USERNAME` 和 `DASHBOARD_PASSWORD`，代码在任一认证值缺失时会拒绝启动。不要把认证值、`.dashboard_auth`、`state.json` 或 `positions.json` 提交到 Git。

**费用与免费版限制（核对日期：2026-10-11）：** Blueprint 使用 0.5 CPU / 512 MB 的常驻 Web Service（Render 标价 US$7/月）和 1 GB 持久 SSD（US$0.25/GB/月），最低配置约 **US$7.25/月**，另可能有超出包含额度的用量费用及税费。Render 免费 Web Service 会在空闲 15 分钟后休眠并丢失本地文件变更，且不支持持久盘，因此不能满足本项目常驻运行和状态长期保存的要求。创建付费服务前须先批准费用。

**上线前后注意：** Render 从 Git 仓库部署；当前工作目录并未配置 Git 仓库或远端。请将代码放入私有 Git 仓库，并确认 `.gitignore` 生效后再连接 Render。认证口令必须通过 Render 的环境变量/Blueprint 提示填写，不能写进仓库。已有 `state.json` 被 `.gitignore` 排除，不会自动传到新实例；若需保留当前纸面持仓和记录，须在服务及持久盘创建后通过安全方式导入到 `/var/data/state.json`。未导入时服务会从 $100 虚拟本金开始。不要把本地状态文件提交到仓库。

部署参数参考：[Render Flask 部署](https://render.com/docs/deploy-flask)、[免费实例限制](https://render.com/docs/free)、[持久磁盘](https://render.com/docs/disks)、[Render 定价](https://render.com/pricing)。
