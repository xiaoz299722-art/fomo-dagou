"""Authenticated paper-only dashboard: stats, positions, equity and log.

The network canvas is a REAL-TIME view of the system, not a prediction:
  input layer  = open positions (live multiple)
  hidden layer = the 4 strategy rules (glow = close to trigger / fired)
  output layer = positions (realized + unrealized P&L)
Edge brightness = trigger proximity. Every pixel is live data.

Run: python run.py dashboard  ->  http://localhost:5001
"""
import hmac
import os
import time
from flask import Flask, jsonify, Response, request

import config

PAGE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>打狗策略看板</title>
<style>
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#0b0e13;color:#e6e6e6;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 4px}.sub{color:#8b93a1;font-size:12px;margin-bottom:12px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.card{background:#141922;border:1px solid #262d38;border-radius:10px;padding:12px 16px;min-width:140px}
.card .k{font-size:12px;color:#8b93a1}.card .v{font-size:22px;font-weight:700;margin-top:4px}
.pos{color:#3ddc84}.neg{color:#ff6b6b}.warn{color:#ffb020}
#net{width:100%;height:340px;background:#0b0e13;border:1px solid #262d38;border-radius:10px;display:block}
table{width:100%;border-collapse:collapse;font-size:13px;background:#141922;border-radius:10px;overflow:hidden;margin-top:8px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #262d38}
th{color:#8b93a1;background:#10151c}
h2{font-size:15px;margin:18px 0 6px}
#eq{width:100%;height:160px;background:#141922;border:1px solid #262d38;border-radius:10px}
form.add{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
form.add input{background:#0b0e13;border:1px solid #262d38;color:#e6e6e6;border-radius:8px;padding:8px 10px;font-size:13px}
form.add button{background:#2f81f7;border:0;color:#fff;border-radius:8px;padding:8px 18px;font-size:13px;cursor:pointer}
.note{color:#8b93a1;font-size:12px;margin-top:14px;line-height:1.7}
.tag{font-size:11px;padding:2px 8px;border-radius:20px;background:#1f2733;color:#8b93a1}
</style></head><body>
<h1>打狗策略执行看板 <span class="tag" id="mode">paper</span></h1>
<div class="sub">规则: 2x卖50% · 3x卖30%(留20%) · 跌50%止损 · 3x后回撤35%清仓 · 数据 10s 刷新</div>
<div class="cards">
<div class="card"><div class="k">已实现</div><div class="v" id="real">-</div></div>
<div class="card"><div class="k">持仓数</div><div class="v" id="posn">-</div></div>
<div class="card"><div class="k">已执行动作</div><div class="v" id="acts">-</div></div>
<div class="card"><div class="k">虚拟总权益(含持仓)</div><div class="v" id="vequity">-</div></div>
<div class="card"><div class="k">可用虚拟现金</div><div class="v" id="vcash">-</div></div>
<div class="card"><div class="k">自动仓</div><div class="v" id="auton">-</div></div>
<div class="card"><div class="k">触发规则</div><div class="v" id="fired" style="font-size:15px">-</div></div>
</div>
<h2>策略神经网络 (实时状态, 非预测)</h2>
<canvas id="net"></canvas>
<h2>持仓</h2>
<table><thead><tr><th>代币</th><th>来源</th><th>现价/成本</th><th>倍数</th><th>峰值</th>
<th>已卖</th><th>前10占比</th><th>下个触发</th><th>规则进度</th></tr></thead>
<tbody id="poss"><tr><td colspan="9">无持仓, 下方添加</td></tr></tbody></table>
<h2>资金曲线 (已实现+持仓市值)</h2><canvas id="eq"></canvas>
<h2>执行记录</h2>
<table><thead><tr><th>时间</th><th>代币</th><th>动作</th><th>价格</th><th>金额</th></tr></thead>
<tbody id="log"><tr><td colspan="5">暂无</td></tr></tbody></table>
<h2>添加仓位</h2>
<form class="add" onsubmit="return addPos(event)">
<input id="f_mint" placeholder="代币 mint 地址" size="46" required>
<input id="f_sym" placeholder="简称(如 BONK)" size="10" required>
<input id="f_entry" placeholder="买入价(空=现价)" size="14">
<input id="f_amt" placeholder="数量(枚)" size="12" required>
<button type="submit">添加</button>
</form>
<div class="note">此部署为纸面专用：不读取私钥、不含实盘执行器，信号与记账均为模拟。
网络图只是系统状态的可视化,
不预测行情、不保证收益。</div>
<script>
const $=id=>document.getElementById(id);
let S=null, pulse=0;
function money(v){return `<span class="${v>=0?'pos':'neg'}">$${v.toFixed(2)}</span>`}
function bar(p){p=Math.max(0,Math.min(1,p));const c=p>0.8?'#ff6b6b':p>0.5?'#ffb020':'#3ddc84';
 return `<div style="background:#0b0e13;border-radius:4px;height:8px;width:90px"><div style="height:8px;width:${(p*100).toFixed(0)}%;background:${c};border-radius:4px"></div></div>`}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function tick(){try{S=await (await fetch('/api/state')).json();render();}catch(e){}}
function render(){
 $('mode').textContent=S.stats.mode;
 $('real').innerHTML=money(S.stats.realized_usd);
 $('posn').textContent=S.stats.open_positions;
 $('acts').textContent=S.stats.closed_actions;
 $('vequity').innerHTML=money(S.stats.virtual_equity_usd);
 $('vcash').innerHTML=money(S.stats.virtual_cash);
 $('auton').textContent=S.stats.auto_open+' / 5';
 const fr=[];S.positions.forEach(p=>{if(p.r1)fr.push(p.symbol+':R1');if(p.r4)fr.push(p.symbol+':R4');});
 $('fired').textContent=fr.length?fr.join(' '):'无';
 $('poss').innerHTML=S.positions.length?S.positions.map(p=>
  `<tr><td><b>${esc(p.symbol)}</b></td><td>${p.source==='auto'?'自动':'手动'}</td><td>${p.price.toFixed(6)} / ${p.entry.toFixed(6)}</td>
   <td class="${p.mult>=1?'pos':'neg'}">${p.mult.toFixed(2)}x</td><td>${p.peak.toFixed(2)}x</td>
   <td>${p.sold_pct}%</td><td>${p.source==='auto'?Number(p.top10_pct||0).toFixed(2)+'%':'—'}</td><td>${esc(p.next_trigger)}</td><td>${bar(Math.max(p.prox.r1,p.prox.r4,p.prox.stop,p.prox.trail))}</td></tr>`).join('')
  :'<tr><td colspan="9">无持仓, 下方添加</td></tr>';
 $('log').innerHTML=S.trades.length?S.trades.slice(-30).reverse().map(t=>
  `<tr><td>${new Date(t.ts*1000).toLocaleString()}</td><td>${esc(t.symbol)}</td><td>${esc(t.reason)}</td>
   <td>${t.price.toFixed(6)}</td><td>${money(t.proceeds_usd)}</td></tr>`).join('')
  :'<tr><td colspan="5">暂无</td></tr>';
 drawNet();drawEq();
}
async function addPos(e){e.preventDefault();
 const b={mint:$('f_mint').value.trim(),symbol:$('f_sym').value.trim(),
  entry:parseFloat($('f_entry').value)||null,amount:parseFloat($('f_amt').value)};
 const r=await fetch('/api/positions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
 const j=await r.json();if(!j.ok)alert(j.reason);else{$('f_mint').value='';tick();}return false;}
/* ---- neural net canvas ---- */
const RULES=[['R1','2x卖50%','#3ddc84'],['R4','3x卖30%','#3ddc84'],['R2','止损','#ff6b6b'],['R3','回撤清','#ffb020']];
function drawNet(){
 const c=$('net'),ctx=c.getContext('2d'),dpr=window.devicePixelRatio||1;
 const W=c.clientWidth,H=c.clientHeight;c.width=W*dpr;c.height=H*dpr;ctx.scale(dpr,dpr);
 ctx.clearRect(0,0,W,H);
 const pos=S?S.positions:[],n=Math.max(pos.length,1);
 const X0=W*0.12,X1=W*0.5,X2=W*0.88;
 const yOf=i=>H*0.12+i*(H*0.76/Math.max(n-1,1))- (n===1?H*0.26:0);
 const ry=j=>H*0.14+j*(H*0.72/3);
 // edges input->hidden
 pos.forEach((p,i)=>{const y=yOf(i);
  const prox=[p.prox.r1,p.prox.r4,p.prox.stop,p.prox.trail];
  prox.forEach((w,j)=>{
   const a=0.06+0.9*w, yy=ry(j);
   ctx.strokeStyle=RULES[j][2]+Math.floor(a*255).toString(16).padStart(2,'0');
   ctx.lineWidth=0.5+3*w;ctx.beginPath();ctx.moveTo(X0,y);ctx.lineTo(X1,yy);ctx.stroke();
  });
 });
 // pulse dots along strongest edges
 pulse=(pulse+0.03)%1;
 pos.forEach((p,i)=>{const y=yOf(i);
  const prox=[p.prox.r1,p.prox.r4,p.prox.stop,p.prox.trail];
  let bj=0,bw=0;prox.forEach((w,j)=>{if(w>bw){bw=w;bj=j;}});
  if(bw>0.25){const yy=ry(bj),px=X0+(X1-X0)*pulse,py=y+(yy-y)*pulse;
   ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(px,py,2.5,0,7);ctx.fill();}
 });
 // hidden nodes (rules)
 RULES.forEach((r,j)=>{const y=ry(j);
  let glow=0;pos.forEach(p=>{glow=Math.max(glow,[p.prox.r1,p.prox.r4,p.prox.stop,p.prox.trail][j]);});
  const g=ctx.createRadialGradient(X1,y,2,X1,y,34);
  g.addColorStop(0,r[2]);g.addColorStop(1,'#0b0e13');
  ctx.globalAlpha=0.25+0.75*glow;ctx.fillStyle=g;
  ctx.beginPath();ctx.arc(X1,y,30,0,7);ctx.fill();ctx.globalAlpha=1;
  ctx.fillStyle='#0b0e13';ctx.font='bold 13px sans-serif';ctx.textAlign='center';
  ctx.fillText(r[0],X1,y-2);
  ctx.fillStyle='#8b93a1';ctx.font='11px sans-serif';ctx.fillText(r[1],X1,y+38);
 });
 // input nodes
 ctx.textAlign='right';
 pos.forEach((p,i)=>{const y=yOf(i);
  ctx.fillStyle=p.mult>=1?'#3ddc84':'#ff6b6b';
  ctx.beginPath();ctx.arc(X0,y,16,0,7);ctx.fill();
  ctx.fillStyle='#0b0e13';ctx.font='bold 11px sans-serif';ctx.textAlign='center';
  ctx.fillText(p.symbol.slice(0,6),X0,y+4);
  ctx.fillStyle='#8b93a1';ctx.font='11px sans-serif';ctx.textAlign='right';
  ctx.fillText(p.mult.toFixed(2)+'x',X0-24,y+4);ctx.textAlign='center';
 });
 // output nodes (P&L)
 pos.forEach((p,i)=>{const y=yOf(i);
  const up=p.realized+p.unreal>=0;
  ctx.fillStyle=up?'#3ddc84':'#ff6b6b';ctx.globalAlpha=0.85;
  ctx.beginPath();ctx.arc(X2,y,16,0,7);ctx.fill();ctx.globalAlpha=1;
  ctx.fillStyle='#0b0e13';ctx.font='bold 10px sans-serif';
  ctx.fillText((up?'+':'')+(p.realized+p.unreal).toFixed(0),X2,y+4);
 });
 // labels
 ctx.fillStyle='#8b93a1';ctx.font='12px sans-serif';ctx.textAlign='center';
 ctx.fillText('持仓(实时倍数)',X0,H-8);ctx.fillText('策略规则',X1,H-8);ctx.fillText('盈亏',X2,H-8);
 if(!pos.length){ctx.fillStyle='#3a4354';ctx.font='14px sans-serif';
  ctx.fillText('添加仓位后, 神经网络点亮',W/2,H/2);}
}
function drawEq(){
 const c=$('eq'),x=c.getContext('2d'),dpr=window.devicePixelRatio||1;
 const W=c.clientWidth,H=c.clientHeight;c.width=W*dpr;c.height=H*dpr;x.scale(dpr,dpr);
 x.clearRect(0,0,W,H);const pts=S?S.equity:[];
 if(!pts.length)return;const vs=pts.map(p=>p[1]);
 const mn=Math.min(...vs,0),mx=Math.max(...vs,0),rg=(mx-mn)||1;
 x.strokeStyle='#3ddc84';x.lineWidth=2;x.beginPath();
 pts.forEach((p,i)=>{const px=i/(pts.length-1||1)*W,py=H-((p[1]-mn)/rg)*(H-16)-8;
  i?x.lineTo(px,py):x.moveTo(px,py);});x.stroke();
}
tick();setInterval(tick,10000);
(function anim(){if(S)drawNet();requestAnimationFrame(anim);})();
</script></body></html>"""


def _prox(p, cfg):
    m = p["mult"]
    return {
        "r1": max(0.0, min(1.0, m / cfg["r1_mult"])),
        "r4": max(0.0, min(1.0, m / cfg["r4_mult"])),
        "stop": max(0.0, min(1.0, (1.0 - m) / (1.0 - cfg["stop_mult"]))) if m < 1 else 0.0,
        "trail": (max(0.0, min(1.0, (p["peak"] - m) / (p["peak"] * cfg["trail_retrace"])))
                  if p["peak"] >= cfg["trail_start"] else 0.0),
    }


def create_app(portfolio, price_cache, lock, cfg):
    app = Flask(__name__)

    env_user = os.getenv("DASHBOARD_USERNAME")
    env_password = os.getenv("DASHBOARD_PASSWORD")
    if env_user is not None or env_password is not None:
        if not env_user or not env_password:
            raise RuntimeError("both dashboard username and password must be configured")
        auth_user, auth_password = env_user, env_password
    else:
        try:
            with open(config.DASHBOARD_AUTH_FILE, encoding="utf-8") as f:
                auth_user, auth_password = f.read().strip().split(":", 1)
        except (OSError, ValueError) as exc:
            raise RuntimeError("dashboard auth file is missing or invalid") from exc
    if not auth_user or not auth_password:
        raise RuntimeError("dashboard auth credentials cannot be empty")

    @app.before_request
    def require_auth():
        # Render's health probe reveals no portfolio or application data.
        if request.endpoint == "healthz":
            return None
        auth = request.authorization
        if (not auth or not hmac.compare_digest(auth.username or "", auth_user)
                or not hmac.compare_digest(auth.password or "", auth_password)):
            return Response("Authentication required", 401,
                            {"WWW-Authenticate": 'Basic realm="FOMO paper dashboard"'})

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/healthz")
    def healthz():
        return Response("ok\n", mimetype="text/plain")

    @app.route("/")
    def index():
        return Response(PAGE, mimetype="text/html")

    @app.route("/api/state")
    def api_state():
        with lock:
            rows = portfolio.position_rows(price_cache)
            for r in rows:
                pos = portfolio.positions[r["mint"]]
                px = price_cache.get(r["mint"], 0) or 0
                unreal = pos.amount * px
                r["realized"] = round(pos.realized_usd, 2)
                r["unreal"] = round(unreal, 2)
                r["prox"] = _prox(r, cfg)
            return jsonify({
                "stats": portfolio.stats(price_cache),
                "positions": rows,
                "trades": portfolio.trades[-100:],
                "equity": portfolio.equity_curve[-500:],
                "ts": time.time(),
            })

    @app.route("/api/positions", methods=["POST"])
    def api_add():
        b = request.get_json(force=True)
        mint = (b.get("mint") or "").strip()
        symbol = (b.get("symbol") or "").strip() or mint[:6]
        amount = float(b.get("amount") or 0)
        entry = b.get("entry")
        if not mint or amount <= 0:
            return jsonify({"ok": False, "reason": "mint/数量无效"})
        if entry is None:
            px = price_cache.get(mint)
            if not px:
                return jsonify({"ok": False, "reason": "取不到现价, 请手动填买入价"})
            entry = px
        with lock:
            ok, reason = portfolio.add_position(mint, symbol, float(entry), amount)
        return jsonify({"ok": ok, "reason": reason})

    return app
