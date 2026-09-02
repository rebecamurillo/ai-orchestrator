#!/usr/bin/env python3
"""Generates the v1 screen artboards (*.dc.html) from one shared stylesheet.
Design system: instrument-dark (DESIGN.md, 2026-08-25). Values lifted verbatim.
Spec: ../EXPERIENCE-v1.md (updated 2026-09-02) — planned runs, composed templates,
instance credentials, Stop table, compare links.
Run: python3 build.py  -> writes Main.dc.html, Login.dc.html, ... next to this file.
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))

CSS = r"""
body{margin:0;background:#0B0D0E;color:#DDE3E5;font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:13px;line-height:1.45;-webkit-font-smoothing:antialiased}
a{color:#7FD4C1;text-decoration:none} a:hover{color:#DDE3E5}
*{box-sizing:border-box}
.app{width:1440px;height:900px;display:grid;grid-template-columns:172px 1fr;background:#0B0D0E;overflow:hidden}
.rail{background:#0E1113;border-right:1px solid #21272A;padding:14px 0 0;display:flex;flex-direction:column}
.brand{padding:0 14px 16px;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#DDE3E5}
.brand span{display:block;color:#5C686C;font-size:10.5px;letter-spacing:.04em;text-transform:none;margin-top:3px}
.nav{display:flex;justify-content:space-between;padding:5px 14px;color:#8B979B;font-size:12px}
.nav.on{color:#DDE3E5;background:#171B1D;box-shadow:inset 2px 0 0 #7FD4C1}
.nav .n{color:#5C686C}
.nav .n.att{color:#E4B33C}
.grp{padding:16px 14px 5px;color:#5C686C;font-size:10px;letter-spacing:.18em;text-transform:uppercase}
.railfoot{margin-top:auto;padding:10px 14px 12px;color:#5C686C;font-size:10.5px;line-height:1.7;border-top:1px solid #21272A}
.railfoot b{color:#8B979B;font-weight:400}
.main{min-width:0;display:flex;flex-direction:column;height:900px;overflow:hidden}
.bar{display:flex;align-items:baseline;gap:16px;padding:12px 16px;border-bottom:1px solid #21272A;flex:none}
.bar h1{margin:0;font-size:13px;letter-spacing:.18em;text-transform:uppercase;font-weight:400}
.count{color:#5C686C;font-size:11.5px}
.spacer{flex:1}
.filters{display:flex;border:1px solid #21272A}
.filters span{border-right:1px solid #21272A;color:#5C686C;font-size:11px;padding:3px 9px;letter-spacing:.08em;white-space:nowrap}
.filters span:last-child{border-right:0}
.filters span.on{background:#171B1D;color:#DDE3E5}
.search{background:#0A0C0D;border:1px solid #21272A;color:#5C686C;font-size:11.5px;padding:3px 8px;width:110px}
.btn{display:inline-block;background:transparent;border:1px solid #2C3438;color:#8B979B;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:4px 10px;white-space:nowrap}
.btn.pri{border-color:#7FD4C1;color:#7FD4C1}
.btn.des{border-color:#E05252;color:#E05252}
.btn.dis{border-color:#21272A;color:#5C686C}
.tok{font-size:11px;letter-spacing:.1em;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.tok i{width:7px;height:7px;display:inline-block;flex:none}
.s-run{color:#4FB477}.s-run i{background:#4FB477}
.s-blk{color:#E4B33C}.s-blk i{background:#E4B33C}
.s-err{color:#E05252}.s-err i{background:#E05252}
.s-que{color:#5C686C}.s-que i{border:1px solid #5C686C}
.s-don{color:#8B979B}.s-don i{border:1px solid #8B979B}
.s-skp{color:#5C686C}.s-skp i{border:1px dashed #5C686C}
.s-can{color:#5C686C}.s-can i{border:1px solid #5C686C;background:#21272A}
.t1{color:#DDE3E5}.t2{color:#8B979B}.t3{color:#5C686C}.ac{color:#7FD4C1}
.amber{color:#E4B33C}.red{color:#E05252}.green{color:#4FB477}
.sec{margin:0 0 30px}
.sec-h{font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:#5C686C;padding-bottom:7px;border-bottom:1px solid #21272A;margin:0 0 12px;display:flex;gap:12px;align-items:baseline}
.sec-h .spacer{flex:1}
.kv{width:100%;border-collapse:collapse}
.kv td{padding:5px 0;font-size:12px;border-bottom:1px solid #21272A}
.kv td:first-child{color:#5C686C;width:44%}
.kv td:last-child{color:#DDE3E5;text-align:right}
table.rec{width:100%;border-collapse:collapse;table-layout:fixed}
.rec th{text-align:left;font-weight:400;color:#5C686C;font-size:10px;letter-spacing:.18em;text-transform:uppercase;padding:7px 10px;border-bottom:1px solid #21272A;background:#0E1113;white-space:nowrap}
.rec td{padding:7px 10px;border-bottom:1px solid #21272A;font-size:12px;color:#8B979B;vertical-align:top;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rec td.r,.rec th.r{text-align:right}
.rec tr.cur td{color:#DDE3E5}
.rec.dense th{padding:5px 8px}
.rec.dense td{padding:4px 8px;font-size:11.5px}
.board{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));flex:1;min-height:0}
.col{border-right:1px solid #21272A;display:flex;flex-direction:column;min-width:0}
.col:last-child{border-right:0}
.colh{display:flex;justify-content:space-between;padding:8px 12px;border-bottom:1px solid #21272A;background:#0E1113;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#5C686C}
.colh.att{color:#E4B33C}
.colh.run{color:#4FB477}
.cards{padding:10px;display:flex;flex-direction:column;gap:8px;overflow:auto}
.card{background:#111416;border:1px solid #21272A;padding:10px 8px;display:flex;flex-direction:column;gap:5px}
.card.att{box-shadow:inset 2px 0 0 #E4B33C}
.card.err{box-shadow:inset 2px 0 0 #E05252}
.card .ttl{font-size:12.5px;color:#DDE3E5;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .meta{font-size:11.5px;color:#5C686C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .step{font-size:11px;color:#8B979B;line-height:1.5}
.card .prog{font-size:11px;color:#5C686C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .foot{display:flex;justify-content:space-between;font-size:11.5px;color:#5C686C}
.card .foot .old{color:#E4B33C}
.empty{color:#5C686C;font-size:11.5px;padding:18px 0 0;text-align:center}
.form{padding:22px 28px 30px;max-width:940px;overflow:auto;flex:1;min-height:0}
.f{display:grid;grid-template-columns:190px 1fr;gap:6px 18px;align-items:start;padding:9px 0;border-bottom:1px solid #21272A}
.f label{color:#5C686C;font-size:11px;letter-spacing:.14em;text-transform:uppercase;padding-top:6px}
.in{background:#0A0C0D;border:1px solid #21272A;color:#DDE3E5;font-size:12.5px;padding:5px 8px;min-height:27px;line-height:1.3}
.in.ph{color:#5C686C}
.in.sel::after{content:"▾";float:right;color:#5C686C}
.in.ta{min-height:64px;white-space:pre-wrap;line-height:1.55}
.hint{color:#5C686C;font-size:11px;margin-top:5px;line-height:1.6}
.hint b{color:#8B979B;font-weight:400}
.seg{display:inline-flex;border:1px solid #21272A}
.seg span{padding:4px 12px;font-size:11px;letter-spacing:.1em;color:#5C686C;border-right:1px solid #21272A;text-transform:uppercase}
.seg span:last-child{border-right:0}
.seg span.on{background:#171B1D;color:#DDE3E5}
.hrl{display:grid;grid-template-columns:16px 64px 1fr auto;gap:0 12px;align-items:baseline;font-size:12px;padding:4px 0}
.hrl .rd{width:9px;height:9px;border:1px solid #5C686C;display:inline-block;border-radius:50%}
.hrl .rd.on{border-color:#DDE3E5;box-shadow:inset 0 0 0 2px #0A0C0D;background:#DDE3E5}
.hrl .rd.dis{border-style:dashed}
.hrl .nm{color:#DDE3E5}
.hrl.dis .nm{color:#5C686C}
.actions{display:flex;gap:8px;padding-top:16px;border-top:1px solid #21272A;margin-top:8px;align-items:center;flex-wrap:wrap}
.actions .note{color:#5C686C;font-size:11px;margin-left:6px}
.banner{background:#171B1D;border-left:2px solid #E4B33C;padding:14px 18px;display:flex;gap:16px;align-items:baseline;font-size:12.5px}
.banner.err{border-left-color:#E05252}
.banner.grey{border-left-color:#2C3438}
.banner .msg{color:#DDE3E5}
.banner .go{margin-left:auto}
.dhead{padding:16px 28px 14px;border-bottom:1px solid #21272A;flex:none}
.crumb{color:#5C686C;font-size:11px;margin-bottom:10px}
.dtitle{font-size:19px;line-height:1.3;color:#DDE3E5;letter-spacing:-.01em;margin:6px 0 8px;display:flex;gap:14px;align-items:baseline}
.dmeta{color:#5C686C;font-size:11.5px;line-height:1.7}
.dmeta b{color:#8B979B;font-weight:400}
.dbody{padding:22px 28px 40px;overflow:auto;flex:1;min-height:0}
.q{background:#171B1D;border-left:2px solid #E4B33C;padding:14px 18px;font-size:14px;line-height:1.7;color:#DDE3E5}
.q .who{display:block;color:#5C686C;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;margin-bottom:8px}
.cmd{background:#08090A;border:1px solid #2C3438}
.cmd .cbar{display:flex;align-items:center;gap:10px;padding:5px 10px;border-bottom:1px solid #21272A;color:#5C686C;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase}
.cmd pre{margin:0;padding:12px 14px;font-size:13px;color:#DDE3E5;overflow-x:auto;line-height:1.7;white-space:pre}
.cmd .p{color:#5C686C}.cmd .fl{color:#7FD4C1}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:26px}
.tree{font-size:12.5px;line-height:1.7;color:#8B979B}
.tree div{display:flex;gap:10px;align-items:center}
.tree .d1{padding-left:14px;border-left:1px solid #21272A;margin-left:4px}
.tree .d2{padding-left:28px;border-left:1px solid #21272A;margin-left:4px}
.tree .new{width:7px;height:7px;background:#7FD4C1;display:inline-block;flex:none}
.tree .ts{margin-left:auto;color:#5C686C;font-size:11px;white-space:nowrap}
.strip{display:flex;gap:4px}
.strip span{flex:1;height:14px;border:1px solid #2C3438;font-size:9px;letter-spacing:.06em;color:#5C686C;display:flex;align-items:center;justify-content:center}
.strip span.d{background:#171B1D;color:#8B979B}
.strip span.b{border-color:#E4B33C;color:#E4B33C}
.strip span.r{border-color:#4FB477;color:#4FB477}
.strip span.s{border-style:dashed;text-decoration:line-through}
.check{display:grid;grid-template-columns:22px 1fr auto;gap:8px 10px;font-size:12px;line-height:1.6;padding:6px 0;border-bottom:1px solid #21272A}
.check .g{color:#8B979B}.check .w{color:#E4B33C}.check .x{color:#E05252}.check .n{color:#5C686C}
.check .out{grid-column:2/4;background:#08090A;border:1px solid #21272A;color:#8B979B;font-size:11.5px;padding:8px 10px;white-space:pre-wrap;overflow:hidden}
.two{display:grid;grid-template-columns:300px 1fr;flex:1;min-height:0}
.list{border-right:1px solid #21272A;overflow:auto}
.li{padding:10px 14px;border-bottom:1px solid #21272A;display:flex;flex-direction:column;gap:3px}
.li.on{background:#171B1D;box-shadow:inset 2px 0 0 #7FD4C1}
.li .ttl{color:#DDE3E5;font-size:12.5px}
.li .meta{color:#5C686C;font-size:11.5px}
.code{background:#0A0C0D;border-right:1px solid #21272A;font-size:12px;line-height:1.65;padding:12px 0;overflow:auto;counter-reset:ln}
.code div{display:grid;grid-template-columns:38px 1fr;white-space:pre}
.code div::before{counter-increment:ln;content:counter(ln);color:#5C686C;text-align:right;padding-right:12px;font-size:11px}
.code .k{color:#8B979B}.code .v{color:#DDE3E5}.code .c{color:#5C686C}.code .s{color:#7FD4C1}
.code div.hl{background:#171B1D;display:grid}
.code.ed{border:1px solid #21272A;border-right:1px solid #21272A;font-size:11.5px;padding:6px 0;line-height:1.6}
.code.ed div{grid-template-columns:30px 1fr;white-space:pre-wrap}
.diag{padding:16px 18px;overflow:auto}
.ltr{display:flex;align-items:center}
.ltr .e{width:14px;height:1px;background:#2C3438;flex:none}
.tn{width:112px;flex:none;border:1px solid #21272A;background:#111416;padding:5px 8px;display:flex;flex-direction:column;gap:2px}
.tn .ty{color:#5C686C;font-size:9.5px;letter-spacing:.14em;text-transform:uppercase}
.tn .nm{color:#DDE3E5;font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tn .gt{color:#5C686C;font-size:10px}
.tn.ag{border-color:#7FD4C1}
.tn.hu{border-color:#2C3438}
.tn.on{background:#171B1D}
.loop{border:1px dashed #2C3438;padding:12px 10px 8px;position:relative;flex:none}
.loop .lbl{position:absolute;top:-8px;left:8px;background:#0B0D0E;padding:0 6px;color:#5C686C;font-size:10px;letter-spacing:.14em;text-transform:uppercase;white-space:nowrap}

.dtree{display:flex;align-items:center;padding:8px 28px 6px;overflow:auto;flex:1;min-height:0}
.row{display:flex;align-items:center}
.kids{display:flex;flex-direction:column;gap:4px;padding-left:30px;position:relative}
.kids::before{content:"";position:absolute;left:15px;top:16px;bottom:16px;width:1px;background:#2C3438}
.kids::after{content:"";position:absolute;left:0;top:50%;width:15px;height:1px;background:#2C3438}
.kid{position:relative}
.kid::before{content:"";position:absolute;left:-15px;top:50%;width:15px;height:1px;background:#2C3438}
.nd{border:1px solid #21272A;background:#111416;padding:4px 10px;display:flex;flex-direction:column;gap:1px;min-width:170px;max-width:272px}
.nd .l1{display:flex;gap:10px;align-items:center;justify-content:space-between;font-size:12px;color:#8B979B;white-space:nowrap}
.nd .l1 .nm{overflow:hidden;text-overflow:ellipsis}
.nd .l2{font-size:10.5px;color:#5C686C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nd.cur{border-color:#2C3438}
.nd.cur .l1{color:#DDE3E5}
.nd .now{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#5C686C}
.nd .sub{display:flex;gap:6px;font-size:9px;letter-spacing:0;color:#5C686C;margin-top:1px;overflow:hidden}
.nd .sub span{white-space:nowrap}
.nd .sub span.on{color:#8B979B}
.nd.sm{min-width:150px;padding:3px 10px}
.nd.xs{min-width:150px;max-width:190px;padding:2px 10px;gap:0}
.nd.xs .l1{font-size:11.5px}
.root{min-width:236px;max-width:none;padding:8px 12px}
.root .l1{font-size:12.5px;color:#DDE3E5}
.heads{display:grid;grid-template-columns:266px 300px 302px 1fr;padding:10px 28px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#5C686C}
.treefoot{padding:8px 28px 10px;border-top:1px solid #21272A;font-size:11.5px;color:#5C686C;display:flex;gap:18px}
.treefoot b{color:#8B979B;font-weight:400}
"""

RAIL_ITEMS = [("workflows", "Workflows", "9"), ("runs", "Runs", "34")]
RAIL_CFG = [("projects", "Projects", "3"), ("templates", "Templates", "4")]


def rail(active, blk_count="2"):
    def item(key, label, n):
        cls = "nav on" if key == active else "nav"
        ncls = "n att" if key == "workflows" else "n"
        nn = f'{n} · <span class="amber">{blk_count} need you</span>' if key == "workflows" else n
        return f'<div class="{cls}" data-testid="nav-{key}"><span>{label}</span><span class="{ncls}">{nn}</span></div>'
    items = "".join(item(*i) for i in RAIL_ITEMS)
    cfg = "".join(item(*i) for i in RAIL_CFG)
    return f'''<nav class="rail" data-testid="nav-rail">
  <div class="brand" data-testid="nav-brand">AI Orchestrator<span>v1 · dev loop · single operator</span></div>
  {items}
  <div class="grp">Configure</div>
  {cfg}
  <div class="railfoot" data-testid="global-run-status"><b>2 running</b> · 2 queued<br>2 need you<br>updated 09:41:12 · <span class="ac">refresh</span></div>
</nav>'''


def page(title, body):
    return f'''<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <title>{title}</title>
  <style>{CSS}</style>
</helmet>
{body}
</x-dc>
</body>
</html>
'''


def tok(cls, label):
    return f'<span class="tok {cls}"><i></i>{label}</span>'


# ---------------------------------------------------------------- LOGIN
LOGIN = page("Login", '''
<div style="width:1440px;height:900px;background:#0B0D0E;display:flex;align-items:center;justify-content:center" data-testid="login-root">
  <div style="width:400px;border:1px solid #2C3438;background:#111416;padding:28px 30px 26px;display:flex;flex-direction:column;gap:18px">
    <div class="brand" style="padding:0">AI Orchestrator<span>v1 · dev loop · single operator</span></div>
    <div style="display:flex;flex-direction:column;gap:6px">
      <label style="color:#5C686C;font-size:11px;letter-spacing:.14em;text-transform:uppercase">Access token</label>
      <div class="in" data-testid="login-token" style="letter-spacing:.2em">••••••••••••••••••••••••</div>
      <div class="hint">Single operator. The token is <b>ORCHESTRATOR_TOKEN</b> from the server environment. Stored in a session cookie, 30 days.</div>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <span class="btn pri" data-testid="login-submit">Enter</span>
      <span class="t3" style="font-size:11px">Enter ↵</span>
    </div>
    <div style="border-top:1px solid #21272A;padding-top:12px;font-size:11.5px;color:#5C686C;line-height:1.7">
      On a rejected token this line reads <span class="red">token rejected — 3 attempts left</span>. Nothing else on the page changes. After the fifth failure it reads <span class="red">too many attempts — try again in 15 min</span> and the input is disabled.
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- BOARD (Main)
def card(cls, status_cls, status, title, meta, step, prog, tmpl, age, old=False, extra=""):
    agecls = "old" if old else ""
    return f'''<div class="card {cls}">
  <div style="display:flex;justify-content:space-between;align-items:center">{tok(status_cls, status)}<span class="t3" style="font-size:10.5px;letter-spacing:.06em">{extra}</span></div>
  <div class="ttl">{title}</div>
  <div class="meta">{meta}</div>
  <div class="step">{step}</div>
  <div class="prog">{prog}</div>
  <div class="foot"><span>{tmpl}</span><span class="{agecls}">{age}</span></div>
</div>'''

FSA = "Fullstack App · optimai/fullstack-app"
AIO = "AI Orchestrator · optimai/ai-orchestrator"
WEB = "Website · optimai/website"

BOARD = page("Workflows", f'''
<div class="app" data-testid="board-root">
  {rail("workflows")}
  <div class="main">
    <div class="bar">
      <h1>Workflows</h1>
      <span class="count" data-testid="board-count">9 runs · 2 need you · oldest wait 2d 04h</span>
      <span class="spacer"></span>
      <span class="search">filter…</span>
      <div class="filters" data-testid="board-filter-project"><span class="on">ALL PROJECTS</span><span>FULLSTACK APP</span><span>AI ORCHESTRATOR</span><span>WEBSITE</span></div>
      <div class="filters"><span class="on">BOARD</span><span>LIST</span></div>
      <span class="btn pri" data-testid="board-new-workflow">+ New workflow</span>
    </div>
    <div class="board">
      <div class="col" data-testid="board-column-queued">
        <div class="colh"><span>Queued</span><span>2</span></div>
        <div class="cards">
          {card("", "s-que", "QUE", "feat/export-csv", FSA, "waiting: repository lock held by feat/saved-views · position 1", "0/1 epics · 0/4 stories · 0 links", "initiative v1", "queued 00h 18m")}
          {card("", "s-que", "QUE", "feat/board-kanban", AIO, "waiting: global concurrency, held by feat/saved-views, chore/repo-init-6.11.0 · position 2", "0/6 stories · 0 links", "epic v1", "queued 00h 06m")}
        </div>
      </div>
      <div class="col" data-testid="board-column-running">
        <div class="colh run"><span>Running</span><span>2</span></div>
        <div class="cards">
          {card("", "s-run", "RUN", "feat/saved-views", FSA, "epic 1 · story 3-2 · build · claude · 00h 42m", "1/2 epics · 5/8 stories · 1 link", "initiative v1", "started 04h 10m ago", extra="claude")}
          {card("", "s-run", "RUN", "chore/repo-init-6.11.0", WEB, "init · shell · 00h 03m", "repo-init", "repo-init v1", "started 00h 03m ago", extra="—")}
        </div>
      </div>
      <div class="col" data-testid="board-column-needs-you">
        <div class="colh att"><span>Needs you</span><span>2</span></div>
        <div class="cards">
          {card("att", "s-blk", "BLK", "feat/notifications-mm", FSA, "epic 2 · story 4-1 · build · blocked · intent gap", "1/2 epics · 5/8 stories · 1 link", "initiative v1", "2d 04h", old=True, extra="claude")}
          {card("att", "s-blk", "CHK", "feat/auth-token", AIO, "story 1-2 · done checkpoint · review and continue", "2/6 stories · 0 links", "epic v1", "03h 12m", extra="local")}
        </div>
      </div>
      <div class="col" data-testid="board-column-done">
        <div class="colh"><span>Done</span><span>1</span></div>
        <div class="cards">
          {card("", "s-don", "DON", "feat/login-token", AIO, "epic 2 · link · done", "2/2 epics · 6/6 stories · 2 links", "initiative v1", "1d 02h", extra="claude")}
        </div>
      </div>
      <div class="col" data-testid="board-column-failed">
        <div class="colh"><span>Failed</span><span>2</span></div>
        <div class="cards">
          {card("err", "s-err", "ERR", "feat/pricing-page", WEB, "epic 1 · baseline · exit 1 before any story ran", "0/1 epics · 0/3 stories · 0 links", "initiative v1", "05h 40m", extra="—")}
          {card("", "s-can", "CAN", "feat/i18n-cleanup", WEB, "cancelled by operator at 09-01 16:20 · epic 1 · story 2-1 · build", "0/1 epics · 1/5 stories · 0 links", "initiative v1", "17h 21m", extra="codex")}
        </div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- NEW WORKFLOW
def f(label, control, hint=""):
    h = f'<div class="hint">{hint}</div>' if hint else ""
    return f'<div class="f"><label>{label}</label><div>{control}{h}</div></div>'

def harness_line(name, state, when, on=False, dis=False):
    rd = "rd on" if on else ("rd dis" if dis else "rd")
    cls = "hrl dis" if dis else "hrl"
    return f'<div class="{cls}" data-testid="newwf-harness-{name}"><span class="{rd}"></span><span class="nm">{name}</span><span class="t2">{state}</span><span class="t3">readiness {when} · <a>re-run</a></span></div>'

HARNESS = "".join([
    harness_line("claude", "enabled", "09-02 08:14", on=True),
    harness_line("codex", "enabled", "09-02 08:14"),
    harness_line("local", "disabled: trace not found", "09-02 08:15", dis=True),
])

def plan_row(path, kind, gate, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<tr{c}><td class="t2">{path}</td><td>{kind}</td><td>{gate}</td></tr>'

PLAN_ROWS = "".join([
    plan_row("plan", "plan.check", "deterministic"),
    plan_row("epics[0].checkout", "git.worktree", "deterministic"),
    plan_row("epics[0].baseline", "shell", "deterministic"),
    plan_row("epics[0].stories[0].sync", "git.sync", "deterministic"),
    plan_row("epics[0].stories[0].build", "agent", "liveness"),
    plan_row("epics[0].stories[0].verify", "shell", "deterministic"),
    plan_row("epics[0].stories[0].commit", "git.commit", "unvalidated"),
    plan_row("epics[0].stories[1..4] · 16 rows", "…", "…"),
    plan_row("epics[0].push", "git.push", "deterministic"),
    plan_row("epics[0].link", "pr.link", "liveness"),
    plan_row("epics[1].checkout", "git.worktree", "deterministic"),
    plan_row("epics[1].baseline", "shell", "deterministic"),
    plan_row("epics[1].stories[0] · 4 rows", "…", "…"),
    plan_row("epics[1].stories[1].build", "agent", "liveness"),
    plan_row("epics[1].stories[1].checkpoint", "human", "human"),
    plan_row("epics[1].stories[2].build", "agent", '<span class="t3">skipped · already done</span>'),
    plan_row("epics[1].push", "git.push", "deterministic"),
    plan_row("epics[1].link", "pr.link", "liveness"),
])

NEWWF = page("New workflow", f'''
<div class="app" data-testid="newwf-root">
  {rail("workflows")}
  <div class="main">
    <div class="bar"><h1>New workflow</h1><span class="count">initiative v1 · a run is one initiative: its epics, their branches, their stories · the plan is fixed at start</span></div>
    <div class="form" style="display:grid;grid-template-columns:1fr 420px;gap:32px;max-width:none">
      <div>
        {f("Template", '<div class="in sel">initiative · v1 — plan every epic in epics.yaml, then every story</div>', "Latest version, pre-selected. Also offered: <b>epic</b>, <b>repo-init</b>. <b>story</b> is not offered — it is called by epic. The run pins this version; later edits never change a run under way.")}
        {f("Project", '<div class="in sel">Fullstack App</div>')}
        {f("Repository", '<div class="in sel">optimai/fullstack-app</div>', "quality_gate_command <b>pnpm run check</b> · test_globs <b>tests/**, **/*.test.*, **/*.spec.*</b> · method <b>6.11.0</b> · one repository per run")}
        {f("Base branch", '<div class="in">main</div>')}
        {f("Initiative folder", '<div class="in">specs/notifications-mm/</div>', "Declared by <b>initiative</b>. Holds <b>epics.yaml</b>: each epic names its branch and spec folder. Choosing <b>epic</b> asks working branch + spec folder here instead.")}
        {f("Harness", HARNESS, "Readiness list. A disabled harness cannot be selected; <b>re-run</b> starts a readiness run on the board.")}
        {f("Model", '<div class="in sel ph">harness default</div>')}
        {f("Budget", '<div class="in" style="width:140px">$ 40.00</div>', "Per run. Breach stops the run: <b>budget $spent / $budget</b> in Needs you.")}
        {f("Re-review done stories", '<div class="seg"><span class="on">OFF</span><span>ON</span></div>', "Off: a story whose file already reads <b>done</b> is planned as <b>skipped · already done</b>.")}
        {f("Manual estimate", '<div class="in ph" style="width:140px">hours, optional</div>', "Writing this yourself, how long? Captured before any token is spent — it cannot be added later.")}
        <div class="actions">
          <span class="btn pri" data-testid="newwf-start">Start run</span>
          <span class="btn">Cancel</span>
          <span class="note">Starts immediately if the repository is free, otherwise queues behind <b>feat/saved-views</b>.</span>
        </div>
      </div>
      <div>
        <div class="sec-h">Pre-flight <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">re-checks on every field change</span></div>
        <div class="check"><span class="g">ok</span><span>origin reachable</span><span class="t3">0.8s</span></div>
        <div class="check"><span class="g">ok</span><span>base branch <span class="ac">main</span> exists</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>epics.yaml parses · 2 epics · notifications, saved-views · spec folders found</span><span class="t3"></span></div>
        <div class="check"><span class="n">—</span><span>branch <span class="ac">feat/notifications</span> does not exist · will be created</span><span class="t3"></span></div>
        <div class="check"><span class="n">—</span><span>branch <span class="ac">feat/saved-views</span> exists · held by run feat/saved-views · queues behind it</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>every stories.yaml parses · 8 stories · ids prefix-free</span><span class="t3"></span></div>
        <div class="check"><span class="w">!</span><span>story <span class="ac">4-2</span> declares spec_checkpoint · run pauses for your review before implementing it</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>SPEC.md in every spec folder</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>harness <span class="ac">claude</span> enabled</span><span class="t3">08:14</span></div>
        <div class="check"><span class="g">ok</span><span>_bmad/ 6.11.0 = image</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>existing story files · 1 done (4-3) · planned as skipped</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>clone check ok · 09-01</span><span class="t3"></span></div>
        <div class="hint" style="margin-top:12px">A red line disables <b>Start run</b> and states the fix (<b>_bmad/</b> outdated: run Initialise repository and merge its branch). A warning never blocks.</div>
        <div class="sec-h" style="margin-top:26px">What will run <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">41 rows · 2 epics · 8 stories</span></div>
        <table class="rec dense" data-testid="newwf-plan"><thead><tr><th style="width:180px">path</th><th style="width:82px">kind</th><th>gate</th></tr></thead>
        <tbody>{PLAN_ROWS}</tbody></table>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- WORKFLOW DETAIL
def step_row(path, kind, gate, scls, s, dur, who, cost, cur=False, note=""):
    c = ' class="cur"' if cur else ""
    st = tok(scls, s) + (f' <span class="t3">{note}</span>' if note else "")
    return f'<tr{c}><td>{path}</td><td>{kind}</td><td>{gate}</td><td>{st}</td><td class="r">{dur}</td><td>{who}</td><td class="r">{cost}</td></tr>'

STEP_ROWS = "".join([
    step_row("plan", "plan.check", "deterministic", "s-don", "DON", "2s", "", "—"),
    step_row("epics[0] · 26 rows · folded · compare", "…", "…", "s-don", "DON", "2h 09m", "claude · sonnet-5", "$5.64"),
    step_row("epics[1].checkout", "git.worktree", "deterministic", "s-don", "DON", "3s", "", "—"),
    step_row("epics[1].baseline", "shell", "deterministic", "s-don", "DON", "1m 09s", "", "—"),
    step_row("epics[1].stories[0].sync", "git.sync", "deterministic", "s-don", "DON", "2s", "", "—"),
    step_row("epics[1].stories[0].build", "agent", "liveness", "s-blk", "BLK", "22m 05s", "claude · sonnet-5", "$2.10", cur=True, note="blocked · 2 attempts"),
    step_row("epics[1].stories[0].verify", "shell", "deterministic", "s-que", "QUE", "", "", ""),
    step_row("epics[1].stories[0].commit", "git.commit", "unvalidated", "s-que", "QUE", "", "", ""),
    step_row("epics[1].stories[1].sync", "git.sync", "deterministic", "s-que", "QUE", "", "", ""),
    step_row("epics[1].stories[1].build", "agent", "liveness", "s-que", "QUE", "", "", "", note="planned · spec checkpoint"),
    step_row("epics[1].stories[1].verify", "shell", "deterministic", "s-que", "QUE", "", "", ""),
    step_row("epics[1].stories[1].commit", "git.commit", "unvalidated", "s-que", "QUE", "", "", ""),
    step_row("epics[1].stories[1].checkpoint", "human", "human", "s-que", "QUE", "", "", ""),
    step_row("epics[1].stories[2].sync", "git.sync", "deterministic", "s-skp", "SKP", "", "", "", note="skipped · already done"),
    step_row("epics[1].stories[2].build", "agent", "liveness", "s-skp", "SKP", "", "", "", note="skipped · already done"),
    step_row("epics[1].stories[2].verify", "shell", "deterministic", "s-skp", "SKP", "", "", "", note="skipped · already done"),
    step_row("epics[1].stories[2].commit", "git.commit", "unvalidated", "s-skp", "SKP", "", "", "", note="skipped · already done"),
    step_row("epics[1].push", "git.push", "deterministic", "s-que", "QUE", "", "", ""),
    step_row("epics[1].link", "pr.link", "liveness", "s-que", "QUE", "", "", ""),
])

def gate_line(t, path, event, actor, text):
    return f'<div><span class="t3" style="flex:none">{t}</span><span class="t2" style="flex:none">{path}</span><span class="t1" style="flex:none">{event}</span><span class="t3" style="flex:none">{actor}</span><span class="t3" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{text}</span></div>'

GATE_LINES = "".join([
    gate_line("08-24 07:12", "plan", "start", "operator", "manual estimate 6h"),
    gate_line("08-24 07:12", "plan", "done", "engine", "2 epics · 8 stories · 41 rows · planned at 3f2a9c1"),
    gate_line("08-24 09:21", "epics[0].link", "done", "engine", "compare main…feat/notifications"),
    gate_line("08-24 09:52", "epics[1].stories[0].build", "blocked", "agent", "intent gap · attempt 1"),
    gate_line("08-24 10:20", "specs/saved-views/SPEC.md", "edit", "operator", 'commit "spec: operator edit (orchestrator)"'),
    gate_line("08-24 10:30", "epics[1].stories[0].build", "resume", "operator", "answer archived · stories/.answers/4-1-attempt-1.md"),
    gate_line("08-24 10:58", "epics[1].stories[0].build", "blocked", "agent", "intent gap · attempt 2"),
])

DETAIL = page("Workflow run", f'''
<div class="app" data-testid="wf-root">
  {rail("workflows")}
  <div class="main">
    <div class="dhead">
      <div class="crumb"><a>← Workflows</a> · run wf_01J9Q3K7</div>
      <div class="dtitle">{tok("s-blk", "BLK")}<span>feat/notifications-mm</span><span class="t3" style="font-size:12px">blocked 2d 04h</span><span class="spacer"></span><div class="filters"><span>DIAGRAM</span><span class="on">DETAIL</span></div></div>
      <div class="dmeta"><b>Fullstack App</b> · optimai/fullstack-app · base <b>main</b> · initiative folder <b>specs/notifications-mm/</b> · template <b>initiative v1</b> · harness <b>claude</b> · started 2026-08-24 07:12 · worktree <b>/work/fullstack-app/wt/feat-notifications-mm</b></div>
    </div>
    <div class="banner" data-testid="wf-alert">
      {tok("s-blk", "BLK")}<span class="msg">blocked · story 4-1 · intent gap</span><span class="go t3">1/2 epics · 5/8 stories · 1 link · $9.84 spent</span>
    </div>
    <div class="dbody" style="padding-top:16px">
      <div class="grid2" style="grid-template-columns:minmax(0,1fr) 400px">
        <div>
          <div class="sec" style="margin-bottom:20px">
            <div class="sec-h">Question <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">## Auto Run Result · verbatim</span></div>
            <div class="q" data-testid="wf-stop-blocked" style="padding:10px 16px"><span class="who">Agent · claude · claude-sonnet-5 · 2026-08-24 10:58 · epic 2 · story 4-1 mattermost-on-block · attempt 2</span>SPEC.md CAP-3 says "a Mattermost message is posted when a story blocks". It does not say which channel, nor whether the operator is also messaged directly. The two readings produce different observable outputs, and nothing in SPEC.md or its companions selects between them.</div>
          </div>
          <div class="sec" style="margin-bottom:20px">
            <div class="sec-h">Answer</div>
            <div class="in ta ph" data-testid="wf-answer" style="min-height:46px">Post to the project's channel only (channel id from project context). No direct message in this story.</div>
            <div class="hint">Archived to <b>specs/saved-views/stories/.answers/4-1-attempt-2.md</b> with your answer; story 4-1 is re-planned with the answer as context. If the gap is in <b>SPEC.md</b>, edit it on the branch in Artifacts instead. Recorded in the gate record.</div>
            <div class="actions"><span class="btn pri" data-testid="wf-resume-with-answer">Resume with answer</span><span class="btn" data-testid="wf-skip-story">Skip story</span><span class="btn" data-testid="wf-skip-epic">Skip epic</span><span class="btn des" data-testid="wf-cancel">Cancel run</span></div>
          </div>
          <div class="sec" style="margin-bottom:20px">
            <div class="sec-h">Or continue in the session <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">session content kept 27d 20h more</span></div>
            <div class="cmd"><div class="cbar">terminal <span class="spacer"></span><span class="btn pri" style="padding:2px 8px">Copy</span></div><pre style="padding:8px 14px"><span class="p">$</span> docker compose exec -w /work/fullstack-app/wt/feat-notifications-mm backend-api claude <span class="fl">--resume</span> 6f2a1c94-3b1e-4c9d-9f0a-2d7e51c0a8b4</pre></div>
            <div class="hint">Execs into <b>backend-api</b>. In progress: <b>Answer, Continue, Skip and Retry disabled until Release — the run resumes by itself when the story file is done and the tree is clean</b>.</div>
          </div>
          <div class="sec">
            <div class="sec-h">Steps <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">41 rows · planned at 3f2a9c1 · gate: liveness = file exists and parses · deterministic = exit code · human = you · unvalidated = no gate</span></div>
            <table class="rec dense" data-testid="wf-steps"><thead><tr><th style="width:200px">path</th><th style="width:82px">kind</th><th style="width:92px">gate</th><th style="width:170px">status</th><th class="r" style="width:58px">time</th><th style="width:112px">harness</th><th class="r" style="width:52px">cost</th></tr></thead>
            <tbody>{STEP_ROWS}</tbody></table>
          </div>
        </div>
        <div>
          <div class="sec">
            <div class="sec-h">Stories 5/8 <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">epic 1 · 5/5 &nbsp; epic 2 · 0/3</span></div>
            <div style="display:grid;grid-template-columns:5fr 3fr;gap:10px">
              <div class="strip"><span class="d">1-1</span><span class="d">1-2</span><span class="d">2-1</span><span class="d">3-1</span><span class="d">3-2</span></div>
              <div class="strip"><span class="b">4-1</span><span>4-2</span><span class="s">4-3</span></div>
            </div>
          </div>
          <div class="sec">
            <div class="sec-h">Artifacts <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">specs/notifications-mm/ · last opened 2d ago</span></div>
            <div class="tree" data-testid="artifacts-tree">
              <div>epics.yaml<span class="ts">read-only · planned at 3f2a9c1</span></div>
              <div>notifications/<span class="ts">epic 1 · 5/5 done</span></div>
              <div class="d1">SPEC.md<span class="ts">08-23 18:02</span></div>
              <div class="d1">stories.yaml<span class="ts">read-only · planned at 3f2a9c1</span></div>
              <div class="d1">stories/<span class="ts">5 done</span></div>
              <div>saved-views/<span class="ts">epic 2 · 0/3</span></div>
              <div class="d1"><span class="t1">SPEC.md</span><span class="ts">open · edited 08-24 10:20</span></div>
              <div class="d1">stories.yaml<span class="ts">read-only · planned at 3f2a9c1</span></div>
              <div class="d1">stories/</div>
              <div class="d2"><span class="new"></span><span class="t1">4-1-mattermost-on-block.md</span><span class="ts">blocked</span></div>
              <div class="d2">.answers/4-1-attempt-1.md<span class="ts">08-24 10:30</span></div>
            </div>
            <div class="code ed" data-testid="wf-editor" style="margin-top:10px">
              <div><span class="k">## CAP-3 Notify on block</span></div>
              <div><span class="v">When a story blocks, post to the project's</span></div>
              <div><span class="v">Mattermost channel (id from project context,</span></div>
              <div class="hl"><span class="v">key mattermost_channel). No direct message.</span></div>
              <div><span class="c"></span></div>
            </div>
            <div class="actions" style="padding-top:10px;margin-top:0;border-top:0"><span class="btn pri" style="padding:2px 8px">Save</span><span class="note">saved as commit "spec: operator edit (orchestrator)" on feat/notifications-mm</span></div>
            <div class="hint">Editable while the run is parked and no terminal session is in progress. <b>stories.yaml</b> and <b>epics.yaml</b> open read-only: planned at 3f2a9c1 — start a new run to change the list.</div>
          </div>
          <div class="sec">
            <div class="sec-h">Cost &amp; trace</div>
            <table class="kv">
              <tr><td>spent / budget</td><td>$9.84 / $40.00</td></tr>
              <tr><td>tokens in / out</td><td>4.1M / 212k <span class="t3">· provisional</span></td></tr>
              <tr><td>wall-clock</td><td>2d 06h 29m</td></tr>
              <tr><td>your active time</td><td>11m</td></tr>
              <tr><td>trace</td><td><a>langfuse · wf_01J9Q3K7</a></td></tr>
              <tr><td>links</td><td>epic 1 <a>compare main…feat/notifications</a> · epic 2 <span class="t3">not pushed</span></td></tr>
              <tr><td>branch</td><td><a>github · feat/notifications-mm</a></td></tr>
            </table>
          </div>
          <div class="sec">
            <div class="sec-h">Gate record <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">time · path · event · actor · text</span></div>
            <div class="tree" style="font-size:11.5px" data-testid="wf-gate-record">{GATE_LINES}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- PROJECTS
PROJECTS = page("Projects", f'''
<div class="app" data-testid="projects-root">
  {rail("projects")}
  <div class="main">
    <div class="bar"><h1>Projects</h1><span class="count">3 projects · 4 repositories</span><span class="spacer"></span><span class="btn" data-testid="projects-edit">Edit</span><span class="btn" data-testid="projects-export">Export trajectories</span><span class="btn pri" data-testid="projects-new">+ New project</span></div>
    <div class="two">
      <div class="list">
        <div class="li on"><span class="ttl">Fullstack App</span><span class="meta">2 repositories · 4 runs · 1 needs you</span></div>
        <div class="li"><span class="ttl">AI Orchestrator</span><span class="meta">1 repository · 4 runs · 1 needs you</span></div>
        <div class="li"><span class="ttl">Website</span><span class="meta">1 repository · 3 runs · <span class="red">1 failed</span></span></div>
      </div>
      <div class="dbody" style="padding:20px 28px">
        <div class="dtitle" style="margin:0 0 4px">Fullstack App</div>
        <div class="dmeta" style="margin-bottom:26px">created 2026-08-20 · spend this month <b>$128.40 / —</b> · log_prompt_content off</div>
        <div class="sec">
          <div class="sec-h">Context <span class="spacer"></span><span class="ac" style="letter-spacing:0;text-transform:none">edit</span></div>
          <div class="t2" style="font-size:12.5px;line-height:1.65;max-width:760px">Internal operations app for OptimAI: projects, clients, invoices. React 19 + Fastify + Postgres, pnpm monorepo. Strategy: ship weekly, every feature behind a flag. Agents must read <span class="ac">docs/architecture.md</span> and <span class="ac">docs/glossary.md</span> before planning. Never touch <span class="ac">packages/billing</span> without a story that names it.</div>
          <div class="hint">Written to <b>project-context.md</b> for every story. Context files are read from the repository at run time.</div>
        </div>
        <div class="sec">
          <div class="sec-h">Repositories <span class="spacer"></span><span class="btn" style="padding:2px 8px">+ Add repository</span></div>
          <table class="rec"><thead><tr><th style="width:176px">repository</th><th style="width:66px">default</th><th style="width:142px">method</th><th style="width:150px">quality_gate_command</th><th style="width:150px">test_globs</th><th style="width:120px">clone check</th><th>status</th></tr></thead>
          <tbody>
            <tr><td class="t1">optimai/fullstack-app</td><td>main</td><td>6.11.0</td><td>pnpm run check</td><td>tests/**, **/*.test.*, **/*.spec.*</td><td>ok · 09-01 · 3.2s</td><td>{tok("s-run","RUN")} feat/saved-views · locked</td></tr>
            <tr><td class="t1">optimai/fullstack-infra</td><td>main</td><td>missing · <a data-testid="projects-init-fullstack-infra">Initialise repository</a></td><td class="t3">— none declared</td><td>tests/**</td><td>ok · 09-01 · 1.1s</td><td><span class="t3">idle · verify step will be <b>skipped</b></span></td></tr>
          </tbody></table>
          <div class="hint"><b>method</b> is the version found in <b>_bmad/</b>; <b>missing</b> or <b>outdated</b> offers Initialise repository (a <b>repo-init</b> run; the row then links to its card and, when done, to its compare link). A <b>failed</b> clone check reads <b>failed · new runs blocked</b> with re-run check. The check runs on save and again daily.</div>
        </div>
        <div class="grid2">
          <div class="sec">
            <div class="sec-h">Settings</div>
            <table class="kv">
              <tr><td>env vars</td><td>3 · masked · <a>show</a></td></tr>
              <tr><td>log_prompt_content</td><td>off</td></tr>
              <tr><td>credentials</td><td>GitHub token and gateway key: instance settings</td></tr>
            </table>
            <div class="hint"><b>Export trajectories</b> downloads <b>trajectories.jsonl</b>, newest first, one line per done story.</div>
          </div>
          <div class="sec">
            <div class="sec-h">Runs on this project</div>
            <table class="kv">
              <tr><td>{tok("s-run","RUN")}</td><td>feat/saved-views · epic 1 · story 3-2 · build</td></tr>
              <tr><td>{tok("s-blk","BLK")}</td><td>feat/notifications-mm · epic 2 · story 4-1 · build</td></tr>
              <tr><td>{tok("s-que","QUE")}</td><td>feat/export-csv</td></tr>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- NEW PROJECT
NEWPROJECT = page("New project", f'''
<div class="app" data-testid="newproject-root">
  {rail("projects")}
  <div class="main">
    <div class="bar"><h1>New project</h1><span class="count">saving runs the clone check on every repository</span></div>
    <div class="form" style="display:grid;grid-template-columns:1fr 400px;gap:32px;max-width:none">
      <div>
        {f("Name", '<div class="in">Website</div>')}
        {f("Context", '<div class="in ta">Marketing site, Astro + Tailwind, deployed on Cloudflare Pages. Copy lives in content/*.mdx; never edit generated i18n files. Strategy: SEO first, no client JS unless a story asks for it.</div>', "What every agent reads before planning. Business intent, architecture, hard rules. Written to <b>project-context.md</b> for every story.")}
        {f("Context files", '<div class="in">docs/architecture.md, docs/glossary.md</div>', "Optional. Paths inside the repository, read at run time.")}
        {f("Agent env vars", '<div class="in ta" style="min-height:44px">NODE_OPTIONS=--max-old-space-size=4096\nPLAYWRIGHT_BROWSERS_PATH=0</div>', "Exported into every agent and shell step for this project. Masked after save.")}
        {f("log_prompt_content", '<div class="seg"><span class="on">OFF</span><span>ON</span></div>', "On: every prompt and completion, including the source code the agent reads, is sent to Langfuse. Off: metadata and cost only.")}
        {f("Credentials", '<div class="t2" style="font-size:12px;padding-top:6px">credentials are instance settings (.env)</div>')}
        <div class="sec-h" style="margin-top:26px">Repositories</div>
        <div style="border:1px solid #21272A;padding:4px 14px 12px;margin-bottom:10px">
          {f("URL", '<div class="in">https://github.com/optimai/website</div>')}
          {f("Default branch", '<div class="in" style="width:200px">main</div>')}
          {f("Package manager", '<div class="seg"><span>npm</span><span class="on">pnpm</span><span>yarn</span><span>uv</span><span>other</span></div>')}
          {f("test_globs", '<div class="in">tests/**, **/*.test.*, **/*.spec.*</div>', "Default pre-filled. An agent change under these paths stops the run: <b>protected path modified</b>.")}
          {f("install_command", '<div class="in">pnpm install --frozen-lockfile</div>', "Runs once per worktree before the baseline.")}
          {f("quality_gate_command", '<div class="in">pnpm run check</div>', "Runs after every story as the deterministic gate. Optional — when absent the verify step is <b>skipped</b>, never green.")}
          {f("unit_test_command", '<div class="in ph">optional</div>')}
        </div>
        <span class="btn">+ Another repository</span>
        <div class="actions"><span class="btn pri" data-testid="project-save">Save project</span><span class="btn">Cancel</span><span class="note">The form keeps every value. A failing repository does not block save.</span></div>
      </div>
      <div>
        <div class="sec-h">Clone check</div>
        <div class="check"><span class="g">ok</span><span>optimai/website · ls-remote · 12 branches</span><span class="t3">0.6s</span></div>
        <div class="check"><span class="g">ok</span><span>optimai/website · shallow clone · 41 MB</span><span class="t3">3.4s</span></div>
        <div class="check"><span class="g">ok</span><span>default branch <span class="ac">main</span> exists</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>method 6.11.0 · _bmad/</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>optimai/website-docs · ls-remote · shallow clone · 6 MB</span><span class="t3">1.2s</span></div>
        <div class="check"><span class="n">—</span><span>method missing → run Initialise repository after save</span><span class="t3"></span></div>
        <div class="check"><span class="x">fail</span><span class="t1">optimai/website-cms · failed · new runs blocked</span><span class="t3">1.9s</span><div class="out">remote: Repository not found.
fatal: Authentication failed for 'https://github.com/optimai/website-cms/'
→ the instance's GitHub token has no access to this repository</div></div>
        <div class="hint" style="margin-top:14px">The project saves anyway; the failing repository reads <b>failed · new runs blocked</b> until <b>re-run check</b> passes. The command output is shown verbatim, never summarised.</div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- RUNS (step/task runs)
def run_row(t, proj, wf, path, kind, harness, scls, s, dur, cost, cur=False):
    c = ' class="cur"' if cur else ""
    return f'<tr{c}><td class="t3">{t}</td><td>{proj}</td><td>{wf}</td><td>{path}</td><td>{kind}</td><td>{harness}</td><td>{tok(scls,s)}</td><td class="r">{dur}</td><td class="r">{cost}</td><td><a>trace</a></td></tr>'

def q_row(pos, proj, wf, step, why, wait):
    return f'<tr><td class="t3">{pos}</td><td>{proj}</td><td>{wf}</td><td>{step}</td><td>{why}</td><td class="r">{wait}</td></tr>'

RUNS = page("Runs", f'''
<div class="app" data-testid="runs-root">
  {rail("runs")}
  <div class="main">
    <div class="bar">
      <h1>Runs</h1>
      <span class="count">every attempt, every workflow · 34 today</span>
      <span class="spacer"></span>
      <span class="search">filter…</span>
      <div class="filters"><span class="on">ALL PROJECTS</span><span>FULLSTACK APP</span><span>AI ORCHESTRATOR</span><span>WEBSITE</span></div>
      <div class="filters"><span class="on">ALL</span><span>QUE</span><span>RUN</span><span>BLK</span><span>ERR</span><span>DON</span></div>
    </div>
    <div class="dbody" style="padding:18px 16px 30px">
      <div class="sec">
        <div class="sec-h">Queue <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">concurrency 2 · one active run per repository · parked runs hold a slot</span></div>
        <table class="rec" data-testid="runs-queue"><thead><tr><th style="width:72px">pos</th><th style="width:136px">project</th><th style="width:200px">workflow</th><th style="width:300px">next step</th><th>waiting because</th><th class="r" style="width:100px">waiting</th></tr></thead>
        <tbody>
          {q_row("slot 1", "Fullstack App", "feat/saved-views", "epics[0].stories[4].build", "running", "—")}
          {q_row("slot 2", "Website", "chore/repo-init-6.11.0", "init", "running", "—")}
          {q_row("1", "Fullstack App", "feat/export-csv", "plan · plan.check", "repository lock held by feat/saved-views", "00h 18m")}
          {q_row("2", "AI Orchestrator", "feat/board-kanban", "plan · plan.check", "global concurrency, held by feat/saved-views, chore/repo-init-6.11.0", "00h 06m")}
          {q_row("—", "Fullstack App", "feat/notifications-mm", "epics[1].stories[0].build · attempt 3", 'waiting for your answer <span class="t3">· not queued until then</span>', "2d 04h")}
          {q_row("—", "AI Orchestrator", "feat/auth-token", "stories[1].checkpoint", 'waiting for your answer <span class="t3">· not queued until then</span>', "03h 12m")}
        </tbody></table>
      </div>
      <div class="sec">
        <div class="sec-h">History <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">one row per attempt · newest first · page 1 of 4</span></div>
        <table class="rec" data-testid="runs-history"><thead><tr><th style="width:100px">time</th><th style="width:118px">project</th><th style="width:176px">workflow</th><th style="width:282px">path</th><th style="width:96px">kind</th><th style="width:140px">harness</th><th style="width:70px">status</th><th class="r" style="width:66px">time</th><th class="r" style="width:60px">cost</th><th style="width:56px">trace</th></tr></thead>
        <tbody>
          {run_row("09:40:51","Fullstack App","feat/saved-views","epics[0].stories[4].build","agent","claude · sonnet-5","s-run","RUN","42m","$1.90", cur=True)}
          {run_row("09:39:02","Website","chore/repo-init-6.11.0","init","shell","","s-run","RUN","3m","—", cur=True)}
          {run_row("09:38:55","Website","chore/repo-init-6.11.0","checkout","git.worktree","","s-don","DON","5s","—")}
          {run_row("08:58:10","Fullstack App","feat/saved-views","epics[0].stories[3].commit","git.commit","","s-don","DON","2s","—")}
          {run_row("08:57:31","Fullstack App","feat/saved-views","epics[0].stories[3].verify","shell","","s-don","DON","1m 04s","—")}
          {run_row("08:31:20","Fullstack App","feat/saved-views","epics[0].stories[3].build","agent","claude · sonnet-5","s-don","DON","25m","$1.61")}
          {run_row("08:31:12","Fullstack App","feat/saved-views","epics[0].stories[3].sync","git.sync","","s-don","DON","3s","—")}
          {run_row("06:20:05","AI Orchestrator","feat/auth-token","stories[1].checkpoint","human","","s-blk","CHK","3h 21m","—")}
          {run_row("06:02:47","AI Orchestrator","feat/auth-token","stories[1].build","agent","local · qwen3-coder","s-don","DON","41m","$0.00")}
          {run_row("04:01:12","Website","feat/pricing-page","epics[0].baseline","shell","","s-err","ERR","48s","—")}
          {run_row("04:00:58","Website","feat/pricing-page","epics[0].checkout","git.worktree","","s-don","DON","6s","—")}
          {run_row("08-24 10:58","Fullstack App","feat/notifications-mm","epics[1].stories[0].build · attempt 2","agent","claude · sonnet-5","s-blk","BLK","28m","$0.80")}
          {run_row("08-24 09:52","Fullstack App","feat/notifications-mm","epics[1].stories[0].build · attempt 1","agent","claude · sonnet-5","s-blk","BLK","22m","$1.30")}
          {run_row("08-24 09:22","Fullstack App","feat/notifications-mm","epics[1].stories[0].sync","git.sync","","s-don","DON","2s","—")}
        </tbody></table>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- TEMPLATES
YAML = [
 ('c', '# initiative · plan every epic in epics.yaml, then every story'),
 ('k', 'name: <v>initiative</v>'), ('k', 'version: <v>1</v>'),
 ('k', 'inputs:'),
 ('k', '  project: <v>{ type: project }</v>'),
 ('k', '  repository: <v>{ type: repository }</v>'),
 ('k', '  base_branch: <v>{ type: string, default: main }</v>'),
 ('k', '  initiative_folder: <v>{ type: path }</v>'),
 ('k', '  harness: <v>{ type: enum, values: [claude, codex, local] }</v>'),
 ('k', '  budget_usd: <v>{ type: number, default: 40 }</v>'),
 ('k', '  re_review: <v>{ type: enum, values: [off, on], default: off }</v>'),
 ('k', '  review_plan: <v>{ type: enum, values: [off, on], default: off }</v>'),
 ('k', 'steps:'),
 ('k', '  - id: <v>plan</v>'),
 ('k', '    uses: <s>plan.check</s>'),
 ('k', '    with: <v>{ file: "{{initiative_folder}}/epics.yaml" }</v>'),
 ('k', '    gate: <v>deterministic</v>'),
 ('k', '  - id: <v>review</v>'),
 ('k', '    uses: <s>human</s>'),
 ('k', '    when: <v>"{{review_plan}} == on"</v>'),
 ('k', '    gate: <v>human</v>'),
 ('k', '  - id: <v>epics</v>'),
 ('k', '    for_each: <v>"{{plan.epics}}"</v>'),
 ('k', '    as: <v>epic</v>'),
 ('k', '    uses: <s>template</s>'),
 ('k', '    with:'),
 ('k', '      name: <v>epic</v>'),
 ('k', '      version: <v>1</v>'),
 ('k', '      working_branch: <v>"{{epic.branch}}"</v>'),
 ('k', '      spec_folder: <v>"{{epic.spec_folder}}"</v>'),
 ('k', '      harness: <v>"{{harness}}"</v>'),
 ('k', '      re_review: <v>"{{re_review}}"</v>'),
 ('k', '  - id: <v>summary</v>'),
 ('k', '    run: <s>git log --oneline "{{base_branch}}..HEAD"</s>'),
 ('c', '    # no gate → unvalidated'),
]
def yaml_lines():
    out = []
    for i, (cls, txt) in enumerate(YAML):
        t = txt.replace('<v>', '<span class="v">').replace('</v>', '</span>').replace('<s>', '<span class="s">').replace('</s>', '</span>')
        hl = ' class="hl"' if 20 <= i <= 30 else ''
        out.append(f'<div{hl}><span class="{cls}">{t}</span></div>')
    return "".join(out)

def tnode(ty, name, gate, cls=""):
    return f'<div class="tn {cls}"><span class="ty">{ty}</span><span class="nm">{name}</span><span class="gt">{gate}</span></div>'

TEMPLATES = page("Templates", f'''
<div class="app" data-testid="templates-root">
  {rail("templates")}
  <div class="main">
    <div class="bar">
      <h1>Templates</h1>
      <span class="count">initiative · v1 · pinned by 4 runs</span>
      <span class="spacer"></span>
      <span class="t3" style="font-size:11px" data-testid="templates-validation">valid · 08:14:02</span>
      <span class="btn">Validate</span>
      <span class="btn pri">Save as v2</span>
    </div>
    <div style="display:grid;grid-template-columns:200px 1fr 560px;flex:1;min-height:0">
      <div class="list">
        <div class="li on"><span class="ttl">initiative</span><span class="meta">v1 · pinned by 4 runs · read-only</span></div>
        <div class="li"><span class="ttl">epic</span><span class="meta">v1 · called by initiative@1 · pinned by 3 runs</span></div>
        <div class="li"><span class="ttl">story</span><span class="meta">v1 · called by epic@1</span></div>
        <div class="li"><span class="ttl">repo-init</span><span class="meta">v1 · pinned by 1 run</span></div>
        <div class="hint" style="padding:12px 14px">A version never changes once a run pins it — directly or as a callee. Saving creates the next version; running workflows keep theirs.</div>
      </div>
      <div class="code">{yaml_lines()}</div>
      <div style="display:flex;flex-direction:column;min-height:0;overflow:auto">
        <div class="diag" style="padding:16px 12px 8px">
          <div class="sec-h">Diagram <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">rendered from the yaml · left-to-right · read-only</span></div>
          <div class="ltr" style="padding:12px 0 4px">
            {tnode("plan.check", "plan", "deterministic")}
            <span class="e"></span>
            {tnode("human", "review", "human", "hu")}
            <span class="e"></span>
            <div class="loop"><span class="lbl">for_each epic</span>{tnode("template", "epic@1", "5 steps · calls story@1", "on")}</div>
            <span class="e"></span>
            {tnode("shell", "summary", "unvalidated")}
          </div>
          <div class="hint" style="margin-top:10px">Teal border = agent step (none at this level; <b>epic@1</b> expands to checkout · baseline · story@1 · push · link). A human gate is the word <b>human</b> and a hairline. Escalation edges all go to <b>Needs you</b>; they are not drawn. A node without a gate reads <b>unvalidated</b>.</div>
        </div>
        <div class="diag" style="padding:8px 12px 12px">
          <div class="sec-h">Inputs bound at start</div>
          <table class="rec dense"><thead><tr><th>name</th><th style="width:90px">type</th><th style="width:150px">default</th></tr></thead><tbody>
            <tr><td class="t1">project</td><td>project</td><td class="t3">required</td></tr>
            <tr><td class="t1">repository</td><td>repository</td><td class="t3">required</td></tr>
            <tr><td class="t1">base_branch</td><td>string</td><td>main</td></tr>
            <tr><td class="t1">initiative_folder</td><td>path</td><td class="t3">required</td></tr>
            <tr><td class="t1">harness</td><td>enum</td><td class="t3">from readiness list</td></tr>
            <tr><td class="t1">budget_usd</td><td>number</td><td>40</td></tr>
            <tr><td class="t1">re_review</td><td>enum</td><td>off</td></tr>
            <tr><td class="t1">review_plan</td><td>enum</td><td>off</td></tr>
          </tbody></table>
          <div class="hint">Callee inputs (<b>epic@1</b>: working_branch, spec_folder; <b>story@1</b>: story · item) are bound by the caller, never at start.</div>
        </div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- USER FLOW
def box(n, title, lines, cls=""):
    return f'''<div style="border:1px solid {'#E4B33C' if cls=='hu' else ('#7FD4C1' if cls=='ag' else '#2C3438')};background:#111416;padding:10px 12px;display:flex;flex-direction:column;gap:4px;min-width:0">
  <div class="t3" style="font-size:10px;letter-spacing:.18em">{n}</div>
  <div class="t1" style="font-size:12.5px;margin-bottom:2px">{title}</div>
  <div class="t2" style="font-size:11px;line-height:1.55">{lines}</div>
</div>'''

FLOW = page("User workflow", f'''
<div style="width:1440px;height:520px;background:#0B0D0E;padding:20px 28px;display:flex;flex-direction:column;gap:16px">
  <div>
    <div class="sec-h">Operator workflow · v1 · what the human does <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">amber = the run needs you</span></div>
    <div style="display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;align-items:start">
      {box("01 · LOGIN", "Enter token", "Once per 30 days.")}
      {box("02 · PROJECTS", "Register project + repositories", "Context, env vars, <b>log_prompt_content</b>. Per repository: default branch, <b>test_globs</b>, install and quality gate commands. No token field: credentials are instance settings. Save runs the clone check, incl. method in <b>_bmad/</b>; missing → <b>Initialise repository</b>.")}
      {box("03 · NEW WORKFLOW", "Bind inputs, start", "Template (<b>initiative</b> pre-selected) · project · repository · base branch · the template's inputs (initiative folder). Harness from the readiness list: <b>enabled</b> / <b>disabled: check</b>. Pre-flight on every change. <b>What will run</b> = the whole plan.")}
      {box("04 · WORKFLOWS", "Walk away, come back", "Green = running, amber = needs you, red = failed. Card: <b>epic 1 · story 3-2 · build · claude · 00h 42m</b> and <b>1/2 epics · 5/8 stories · 1 link</b>. DIAGRAM shows the run as a tree.")}
      {box("05 · RUN DETAIL", "Answer, continue, retry, cancel", "The banner names the Stop. Blocked: question, <b>Answer</b>, <b>Resume with answer</b>. Checkpoint: story file inline, <b>Continue</b> / <b>Reject with a reason</b>. Errored step: output, <b>Retry</b>. Every stop: its skips, <b>Cancel run</b>, spec files editable while parked. Secondary: resume command into backend-api.", "hu")}
      {box("06 · DONE", "Review the branches", "<b>DON</b> card: <b>2/2 epics · 8/8 stories · 2 links</b>. One compare link per epic; skipped stories listed beside it. Opening the pull request and merging are yours, in GitHub.")}
    </div>
  </div>
  <div>
    <div class="sec-h">What the machine does in between · initiative → epic → story <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">teal = agent · grey = deterministic</span></div>
    <div style="display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:10px;align-items:start">
      {box("RUN", "plan", "plan.check: parse the lists, expand loops, persist rows.")}
      {box("PER EPIC", "checkout", "git.worktree on the epic's branch, from base if new.")}
      {box("PER EPIC", "baseline", "quality gate, clean tree. Exit ≠ 0 = ERR.")}
      {box("PER STORY", "sync", "git.sync with origin. Diverged → BLK.")}
      {box("PER STORY", "build", "bmad-build-auto via claude / codex / local. <b>blocked</b> → BLK.", "ag")}
      {box("PER STORY", "verify", "quality gate. <b>verify failed 2/2</b> → BLK. No command → skipped.")}
      {box("PER STORY", "commit", "spec folder + code. done_checkpoint → CHK.")}
      {box("PER EPIC", "push · link", "epic branch to origin, one compare link. Rejected → BLK.")}
      {box("ALWAYS", "trace + cost", "One Langfuse trace per run. Budget breach → BLK.")}
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- RUN DIAGRAM
def nd(name, meta, scls, s, cur=False, sub=None, now=False, cls=""):
    c = " cur" if cur else ""
    subrow = ""
    if sub:
        subrow = '<div class="sub">' + "".join(f'<span class="{"on" if k else ""}">{lbl} {k or "—"}</span>' for lbl, k in sub) + '</div>'
    nowl = ' <span class="now">now</span>' if now else ""
    l2 = f'<div class="l2">{meta}</div>' if meta else ""
    return f'<div class="nd{c} {cls}"><div class="l1"><span class="nm">{name}{nowl}</span>{tok(scls, s)}</div>{l2}{subrow}</div>'

def story(id_, title, scls, s, sub, cur=False, now=False, meta=""):
    return f'<div class="kid">{nd(f"{id_} · {title}", meta, scls, s, cur=cur, sub=sub, now=now)}</div>'

D = [("sync","done"),("build","done"),("verify","done"),("commit","done")]
Q = [("sync",""),("build",""),("verify",""),("commit","")]
RUNDIAGRAM = page("Run diagram", f"""
<div class="app" data-testid="wfdiag-root">
  {rail("workflows")}
  <div class="main">
    <div class="dhead" style="padding:12px 28px 10px">
      <div class="crumb" style="margin-bottom:4px"><a>← Workflows</a> · run wf_01J9Q3K7</div>
      <div class="dtitle" style="margin:2px 0 4px">{tok("s-blk", "BLK")}<span>feat/notifications-mm</span><span class="t3" style="font-size:12px">blocked 2d 04h</span><span class="spacer"></span><div class="filters"><span class="on">DIAGRAM</span><span>DETAIL</span></div></div>
      <div class="dmeta" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><b>Fullstack App</b> · optimai/fullstack-app · base <b>main</b> · initiative folder <b>specs/notifications-mm/</b> · template <b>initiative v1</b> · harness <b>claude</b> · started 2026-08-24 07:12 · worktree <b>/work/fullstack-app/wt/feat-notifications-mm</b></div>
    </div>
    <div class="banner" style="padding:9px 18px">{tok("s-blk", "BLK")}<span class="msg">blocked · story 4-1 · intent gap · switch to DETAIL to answer</span><span class="go t3">1/2 epics · 5/8 stories · 1 link · $9.84 spent</span></div>
    <div class="heads"><span>Run</span><span>Epics</span><span>Stories</span><span>Steps</span></div>
    <div class="dtree">
      <div class="row">
        <div class="nd root"><div class="l1"><span class="nm">feat/notifications-mm</span>{tok("s-blk","BLK")}</div><div class="l2">initiative v1 · 1/2 epics · 5/8 stories · 1 link</div></div>
        <div class="kids">
          <div class="kid">{nd("plan", "plan.check · 2s · 41 rows", "s-don", "DON", cls="sm")}</div>
          <div class="kid"><div class="row">{nd("epic 1 · notifications", "feat/notifications · 5/5 stories · compare", "s-don", "DON")}<div class="kids">
            <div class="kid">{nd("checkout · baseline", "git.worktree 4s · shell 1m 12s", "s-don", "DON", cls="sm")}</div>
            {story("1-1", "mattermost client", "s-don", "DON", D)}
            {story("1-2", "project channel config", "s-don", "DON", D)}
            {story("2-1", "block event", "s-don", "DON", D)}
            {story("3-1", "message template", "s-don", "DON", D)}
            {story("3-2", "retry on 5xx", "s-don", "DON", D)}
            <div class="kid">{nd("push · link", "git.push 6s · pr.link · compare", "s-don", "DON", cls="sm")}</div>
          </div></div></div>
          <div class="kid"><div class="row">{nd("epic 2 · saved-views", "feat/saved-views · 0/3 stories · 1 blocked", "s-blk", "BLK", cur=True)}<div class="kids">
            <div class="kid">{nd("checkout · baseline", "git.worktree 3s · shell 1m 09s", "s-don", "DON", cls="sm")}</div>
            <div class="kid"><div class="row">{nd("4-1 · mattermost on block", "agent · claude · attempt 2", "s-blk", "BLK", cur=True, sub=[("sync","done"),("build","blocked"),("verify",""),("commit","")])}<div class="kids">
              <div class="kid">{nd("sync · 2s", "", "s-don", "DON", cls="xs")}</div>
              <div class="kid">{nd("build · 22m 05s", "", "s-blk", "BLK", cur=True, now=True, cls="xs")}</div>
              <div class="kid">{nd("verify", "", "s-que", "QUE", cls="xs")}</div>
              <div class="kid">{nd("commit", "", "s-que", "QUE", cls="xs")}</div>
            </div></div></div>
            {story("4-2", "operator direct message", "s-que", "QUE", Q + [("checkpoint","")])}
            {story("4-3", "silence window", "s-skp", "SKP", None, meta="skipped · already done")}
            <div class="kid">{nd("push · link", "git.push · pr.link", "s-que", "QUE", cls="sm")}</div>
          </div></div></div>
        </div>
      </div>
    </div>
    <div class="treefoot"><span>step <b>29 of 41</b></span><span><b>epic 2 · story 4-1 · build</b></span><span><b>blocked</b> 2d 04h</span><span><b>5/8</b> stories</span><span class="spacer"></span><span>token = the node's only signal · <b>now</b> marks the current node · QUE = scheduled · click a node → DETAIL at that path</span></div>
  </div>
</div>
""")

FILES = {
    "Flow.dc.html": FLOW,
    "Login.dc.html": LOGIN,
    "Main.dc.html": BOARD,
    "NewWorkflow.dc.html": NEWWF,
    "RunDetail.dc.html": DETAIL,
    "RunDiagram.dc.html": RUNDIAGRAM,
    "Projects.dc.html": PROJECTS,
    "NewProject.dc.html": NEWPROJECT,
    "Runs.dc.html": RUNS,
    "Templates.dc.html": TEMPLATES,
}
for name, content in FILES.items():
    with open(os.path.join(HERE, name), "w") as fh:
        fh.write(content)
    print("wrote", name, len(content))
