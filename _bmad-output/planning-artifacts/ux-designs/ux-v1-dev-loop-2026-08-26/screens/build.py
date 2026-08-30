#!/usr/bin/env python3
"""Generates the v1 screen artboards (*.dc.html) from one shared stylesheet.
Design system: instrument-dark (DESIGN.md, 2026-08-25). Values lifted verbatim.
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
.search{background:#0A0C0D;border:1px solid #21272A;color:#5C686C;font-size:11.5px;padding:3px 8px;width:190px}
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
.board{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));flex:1;min-height:0}
.col{border-right:1px solid #21272A;display:flex;flex-direction:column;min-width:0}
.col:last-child{border-right:0}
.colh{display:flex;justify-content:space-between;padding:8px 12px;border-bottom:1px solid #21272A;background:#0E1113;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#5C686C}
.colh.att{color:#E4B33C}
.colh.run{color:#4FB477}
.cards{padding:10px;display:flex;flex-direction:column;gap:8px;overflow:auto}
.card{background:#111416;border:1px solid #21272A;padding:10px;display:flex;flex-direction:column;gap:5px}
.card .ttl{font-size:12.5px;color:#DDE3E5;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .meta{font-size:11.5px;color:#5C686C;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .step{font-size:11.5px;color:#8B979B;line-height:1.5}
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
.actions{display:flex;gap:8px;padding-top:16px;border-top:1px solid #21272A;margin-top:8px;align-items:center}
.actions .note{color:#5C686C;font-size:11px;margin-left:6px}
.banner{background:#171B1D;border-left:2px solid #E4B33C;padding:14px 18px;display:flex;gap:16px;align-items:baseline;font-size:12.5px}
.banner.err{border-left-color:#E05252}
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
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:26px}
.tree{font-size:12.5px;line-height:1.7;color:#8B979B}
.tree div{display:flex;gap:10px;align-items:center}
.tree .d1{padding-left:14px;border-left:1px solid #21272A;margin-left:4px}
.tree .d2{padding-left:28px;border-left:1px solid #21272A;margin-left:4px}
.tree .new{width:7px;height:7px;background:#7FD4C1;display:inline-block;flex:none}
.tree .ts{margin-left:auto;color:#5C686C;font-size:11px}
.strip{display:flex;gap:4px}
.strip span{flex:1;height:14px;border:1px solid #2C3438;font-size:9px;letter-spacing:.06em;color:#5C686C;display:flex;align-items:center;justify-content:center}
.strip span.d{background:#171B1D;color:#8B979B}
.strip span.b{border-color:#E4B33C;color:#E4B33C}
.strip span.r{border-color:#4FB477;color:#4FB477}
.check{display:grid;grid-template-columns:22px 1fr auto;gap:8px 10px;font-size:12px;line-height:1.6;padding:6px 0;border-bottom:1px solid #21272A}
.check .g{color:#8B979B}.check .w{color:#E4B33C}.check .x{color:#E05252}.check .n{color:#5C686C}
.check .out{grid-column:2/4;background:#08090A;border:1px solid #21272A;color:#8B979B;font-size:11.5px;padding:8px 10px;white-space:pre;overflow:hidden}
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
.code div.hl{background:#171B1D}
.diag{padding:16px 18px;overflow:auto}
.node{border:1px solid #2C3438;background:#111416;padding:6px 10px;font-size:11.5px;color:#DDE3E5;display:flex;gap:10px;align-items:baseline;width:250px}
.node .ty{color:#5C686C;font-size:10px;letter-spacing:.14em;text-transform:uppercase;width:70px;flex:none}
.node .gt{margin-left:auto;color:#5C686C;font-size:10px}
.node.ag{border-color:#7FD4C1}
.node.hu{border-color:#E4B33C}
.edge{width:1px;height:14px;background:#2C3438;margin-left:125px}
.loop{border:1px dashed #2C3438;padding:10px 12px 12px;margin:0 0 0 0;width:274px;position:relative}

.tree{display:flex;align-items:center;padding:26px 28px 10px;overflow:auto;flex:1;min-height:0}
.row{display:flex;align-items:center}
.kids{display:flex;flex-direction:column;gap:6px;padding-left:30px;position:relative}
.kids::before{content:"";position:absolute;left:15px;top:18px;bottom:18px;width:1px;background:#2C3438}
.kids::after{content:"";position:absolute;left:0;top:50%;width:15px;height:1px;background:#2C3438}
.kid{position:relative}
.kid::before{content:"";position:absolute;left:-15px;top:50%;width:15px;height:1px;background:#2C3438}
.nd{border:1px solid #21272A;background:#111416;padding:6px 10px;display:flex;flex-direction:column;gap:3px;min-width:170px;max-width:230px}
.nd .l1{display:flex;gap:10px;align-items:center;justify-content:space-between;font-size:12px;color:#8B979B;white-space:nowrap}
.nd .l1 .nm{overflow:hidden;text-overflow:ellipsis}
.nd .l2{font-size:10.5px;color:#5C686C;white-space:nowrap}
.nd.cur{border-color:#2C3438}
.nd.cur .l1{color:#DDE3E5}
.nd .now{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#5C686C}
.nd .sub{display:flex;gap:10px;font-size:10px;letter-spacing:.06em;color:#5C686C;margin-top:2px}
.nd .sub span{white-space:nowrap}
.nd .sub span.on{color:#8B979B}
.root{min-width:200px;padding:10px 12px}
.root .l1{font-size:12.5px;color:#DDE3E5}
.heads{display:grid;grid-template-columns:230px 260px 260px 1fr;padding:10px 28px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#5C686C}
.treefoot{padding:10px 28px 14px;border-top:1px solid #21272A;font-size:11.5px;color:#5C686C;display:flex;gap:18px}
.treefoot b{color:#8B979B;font-weight:400}
.loop .lbl{position:absolute;top:-8px;left:10px;background:#0B0D0E;padding:0 6px;color:#5C686C;font-size:10px;letter-spacing:.14em;text-transform:uppercase}
"""

RAIL_ITEMS = [("workflows", "Workflows", "7"), ("runs", "Runs", "31")]
RAIL_CFG = [("projects", "Projects", "3"), ("templates", "Templates", "3")]


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
  <div class="railfoot" data-testid="global-run-status"><b>2 running</b> · 1 queued<br>2 need you<br>updated 09:41:12 · <span class="ac">refresh</span></div>
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
      On a rejected token this line reads <span class="red">token rejected — 3 attempts left</span>. Nothing else on the page changes.
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- BOARD (Main)
def card(cls, status_cls, status, title, meta, step, age, old=False, extra=""):
    agecls = "old" if old else ""
    return f'''<div class="card {cls}">
  <div style="display:flex;justify-content:space-between;align-items:center">{tok(status_cls, status)}<span class="t3" style="font-size:10.5px;letter-spacing:.06em">{extra}</span></div>
  <div class="ttl">{title}</div>
  <div class="meta">{meta}</div>
  <div class="step">{step}</div>
  <div class="foot"><span>dev-loop v3</span><span class="{agecls}">{age}</span></div>
</div>'''

BOARD = page("Workflows", f'''
<div class="app" data-testid="board-root">
  {rail("workflows")}
  <div class="main">
    <div class="bar">
      <h1>Workflows</h1>
      <span class="count" data-testid="board-count">7 runs · 2 need you · oldest wait 2d 04h</span>
      <span class="spacer"></span>
      <span class="search">filter…</span>
      <div class="filters" data-testid="board-filter-project"><span class="on">ALL PROJECTS</span><span>FULLSTACK APP</span><span>AI ORCHESTRATOR</span><span>WEBSITE</span></div>
      <div class="filters"><span class="on">BOARD</span><span>LIST</span></div>
      <span class="btn pri" data-testid="board-new-workflow">+ New workflow</span>
    </div>
    <div class="board">
      <div class="col" data-testid="board-column-queued">
        <div class="colh"><span>Queued</span><span>1</span></div>
        <div class="cards">
          {card("", "s-que", "QUE", "feat/export-csv", "Fullstack App · optimai/fullstack-app", "waiting: repository lock held by feat/saved-views · position 1", "queued 00h 18m")}
        </div>
      </div>
      <div class="col" data-testid="board-column-running">
        <div class="colh run"><span>Running</span><span>2</span></div>
        <div class="cards">
          {card("", "s-run", "RUN", "feat/saved-views", "Fullstack App · optimai/fullstack-app", "story 3-2 · build · claude · 00h 42m<br><span class='t3'>5/8 stories done</span>", "started 04h 10m ago", extra="claude")}
          {card("", "s-run", "RUN", "feat/board-kanban", "AI Orchestrator · optimai/ai-orchestrator", "story 2-1 · verify · quality gate · 00h 01m<br><span class='t3'>3/6 stories done</span>", "started 01h 55m ago", extra="codex")}
        </div>
      </div>
      <div class="col" data-testid="board-column-needs-you">
        <div class="colh att"><span>Needs you</span><span>2</span></div>
        <div class="cards">
          {card("att", "s-blk", "BLK", "feat/notifications-mm", "Fullstack App · optimai/fullstack-app", "story 4-1 · build · intent gap — agent asked a question<br><span class='t3'>5/8 stories done</span>", "2d 04h", old=True, extra="claude")}
          {card("att", "s-blk", "CHK", "feat/auth-token", "AI Orchestrator · optimai/ai-orchestrator", "checkpoint after story 1-2 · review and continue<br><span class='t3'>2/6 stories done</span>", "03h 12m", extra="local")}
        </div>
      </div>
      <div class="col" data-testid="board-column-done">
        <div class="colh"><span>Done</span><span>1</span></div>
        <div class="cards">
          {card("", "s-don", "DON", "feat/login-token", "AI Orchestrator · optimai/ai-orchestrator", "6/6 stories · pushed · <span class='ac'>PR #41</span>", "1d 02h", extra="claude")}
        </div>
      </div>
      <div class="col" data-testid="board-column-failed">
        <div class="colh"><span>Failed</span><span>1</span></div>
        <div class="cards">
          {card("err", "s-err", "ERR", "feat/pricing-page", "Website · optimai/website", "baseline · quality gate exit 1 before any story ran", "05h 40m", extra="—")}
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

NEWWF = page("New workflow", f'''
<div class="app" data-testid="newwf-root">
  {rail("workflows")}
  <div class="main">
    <div class="bar"><h1>New workflow</h1><span class="count">dev-loop v3 · a run is one working branch, one repository, one spec folder</span></div>
    <div class="form" style="display:grid;grid-template-columns:1fr 360px;gap:32px;max-width:none">
      <div>
        {f("Template", '<div class="in sel">dev-loop · v3 — implement every story in stories.yaml, auto mode</div>', "Latest version. The run pins this version; later edits never change a run under way.")}
        {f("Project", '<div class="in sel">Fullstack App</div>')}
        {f("Repository", '<div class="in sel">optimai/fullstack-app</div>', "quality_gate_command declared: <b>pnpm run check</b> · one repository per run in v1")}
        {f("Base branch", '<div class="in">main</div>')}
        {f("Working branch", '<div class="in">feat/notifications-mm</div>', "Created from the base branch if it does not exist; checked out if it does.")}
        {f("Spec folder", '<div class="in">specs/notifications/</div>', "Artifact destination. Agents write only here and in the code they change. Path relative to the repository root.")}
        {f("Epics file", '<div class="in">specs/notifications/epics.md</div>', "Optional. Passed to agents as planning context.")}
        {f("Stories file", '<div class="in">specs/notifications/stories.yaml</div>', "Required. Execution order is the list order. <b>spec_checkpoint</b> / <b>done_checkpoint</b> entries pause the run for you.")}
        {f("Harness", '<div class="seg"><span class="on">claude</span><span>codex</span><span>local</span></div>', "All three route through LiteLLM and trace to Langfuse under this run's id.")}
        {f("Model", '<div class="in sel ph">harness default</div>')}
        {f("Budget", '<div class="in" style="width:140px">$ 40.00</div>', "Per run. Breach halts the run and puts it in Needs you.")}
        {f("Manual estimate", '<div class="in ph" style="width:140px">hours, optional</div>', "Writing this yourself, how long? Captured before any token is spent — it cannot be added later.")}
        <div class="actions">
          <span class="btn pri" data-testid="newwf-start">Start run</span>
          <span class="btn">Cancel</span>
          <span class="note">Starts immediately if the repository is free, otherwise queues behind the run holding it.</span>
        </div>
      </div>
      <div>
        <div class="sec-h">Pre-flight <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">re-checks on every field change</span></div>
        <div class="check"><span class="g">ok</span><span>origin reachable · token valid</span><span class="t3">0.8s</span></div>
        <div class="check"><span class="g">ok</span><span>base branch <span class="ac">main</span> exists</span><span class="t3"></span></div>
        <div class="check"><span class="n">—</span><span>working branch does not exist · will be created</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>stories.yaml parsed · 8 stories · ids prefix-free</span><span class="t3"></span></div>
        <div class="check"><span class="w">!</span><span>story <span class="ac">4-2</span> has spec_checkpoint · run pauses for your review before implementing it</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>SPEC.md found · 3 companions</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>epics.md found</span><span class="t3"></span></div>
        <div class="check"><span class="g">ok</span><span>harness <span class="ac">claude</span> available · litellm key for Fullstack App</span><span class="t3"></span></div>
        <div class="hint" style="margin-top:14px">A red line disables <b>Start run</b> and states the fix. A warning never blocks.</div>
        <div class="sec-h" style="margin-top:30px">What will run</div>
        <div class="tree" style="font-size:12px">
          <div><span class="t3">01</span> checkout · git.worktree</div>
          <div><span class="t3">02</span> baseline · shell · pnpm run check</div>
          <div><span class="t3">03</span> for each of 8 stories</div>
          <div class="d1"><span class="t3">a</span> build · agent · bmad-build-auto</div>
          <div class="d1"><span class="t3">b</span> verify · shell · pnpm run check</div>
          <div class="d1"><span class="t3">c</span> commit · git</div>
          <div><span class="t3">04</span> push · git · open PR link</div>
        </div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- WORKFLOW DETAIL
def step_row(n, name, typ, gate, scls, s, dur, who, cost, cur=False):
    c = ' class="cur"' if cur else ""
    return f'<tr{c}><td class="t3">{n}</td><td>{name}</td><td>{typ}</td><td>{gate}</td><td>{tok(scls, s)}</td><td class="r">{dur}</td><td>{who}</td><td class="r">{cost}</td></tr>'

DETAIL = page("Workflow run", f'''
<div class="app" data-testid="wf-root">
  {rail("workflows")}
  <div class="main">
    <div class="dhead">
      <div class="crumb"><a>← Workflows</a> · run wf_01J9Q3K7</div>
      <div class="dtitle">{tok("s-blk", "BLK")}<span>feat/notifications-mm</span><span class="t3" style="font-size:12px">blocked 2d 04h</span></div>
      <div class="dmeta"><b>Fullstack App</b> · optimai/fullstack-app · base <b>main</b> · spec <b>specs/notifications/</b> · template <b>dev-loop v3</b> · harness <b>claude</b> · started 2026-08-24 07:12 · worktree <b>/work/fullstack-app/wt/feat-notifications-mm</b></div>
    </div>
    <div class="banner" data-testid="wf-alert">
      {tok("s-blk", "BLK")}<span class="msg">Story 4-1 stopped with an intent gap. Answer below and the run resumes on its own.</span><span class="go t3">5/8 stories done · $9.84 spent</span>
    </div>
    <div class="dbody">
      <div class="grid2" style="grid-template-columns:1fr 380px">
        <div>
          <div class="sec">
            <div class="sec-h">Question</div>
            <div class="q" data-testid="wf-question"><span class="who">Agent · claude · claude-sonnet-5 · 2026-08-24 09:52 · story 4-1 mattermost-on-block</span>SPEC.md CAP-3 says "a Mattermost message is posted when a story blocks". It does not say which channel, nor whether the operator is also messaged directly. The two readings produce different observable outputs, and nothing in SPEC.md or its companions selects between them.</div>
          </div>
          <div class="sec">
            <div class="sec-h">Answer</div>
            <div class="in ta ph" data-testid="wf-answer">Post to the project's channel only (channel id from project context). No direct message in this story.</div>
            <div class="hint">The blocked story file is archived to <b>specs/notifications/stories/.answers/4-1-attempt-1.md</b> with your answer; story 4-1 is re-planned by the same harness with the answer as context. If the gap is in <b>SPEC.md</b>, edit it on the branch instead. Recorded in the gate record.</div>
            <div class="actions"><span class="btn pri" data-testid="wf-resume-with-answer">Resume with answer</span><span class="btn">Skip story</span><span class="btn des">Cancel run</span></div>
          </div>
          <div class="sec">
            <div class="sec-h">Or continue in the session <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">session content kept 27d 20h more</span></div>
            <div class="cmd"><div class="cbar">terminal <span class="spacer"></span><span class="btn pri" style="padding:2px 8px">Copy</span></div><pre><span class="p">$</span> docker compose exec -w /work/fullstack-app/wt/feat-notifications-mm orchestrator claude <span class="fl">--resume</span> 6f2a1c94-3b1e-4c9d-9f0a-2d7e51c0a8b4</pre></div>
            <div class="hint">Runs inside the orchestrator container. While a terminal session is in progress the buttons above are disabled until <b>Release</b>; when the story reads done on a clean tree, the run resumes on its own.</div>
          </div>
          <div class="sec">
            <div class="sec-h">Steps <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">gate: liveness = file exists and parses · deterministic = command exit code · human = you</span></div>
            <table class="rec"><thead><tr><th style="width:34px">#</th><th style="width:170px">Step</th><th style="width:100px">Type</th><th style="width:110px">Gate</th><th style="width:76px">Status</th><th class="r" style="width:70px">Time</th><th style="width:120px">Harness</th><th class="r" style="width:64px">Cost</th></tr></thead>
            <tbody>
              {step_row("01", "checkout", "git.worktree", "deterministic", "s-don", "DON", "4s", "—", "—")}
              {step_row("02", "baseline", "shell", "deterministic", "s-don", "DON", "1m 12s", "—", "—")}
              {step_row("03", "story 1-1 · build", "agent", "liveness", "s-don", "DON", "18m 40s", "claude · sonnet-5", "$1.42")}
              {step_row("04", "story 1-1 · verify", "shell", "deterministic", "s-don", "DON", "58s", "—", "—")}
              {step_row("…", "stories 1-2 → 3-2", "", "", "s-don", "DON", "2h 51m", "claude · sonnet-5", "$6.32")}
              {step_row("15", "story 4-1 · build", "agent", "liveness", "s-blk", "BLK", "22m 05s", "claude · sonnet-5", "$2.10", cur=True)}
              {step_row("16", "story 4-1 · verify", "shell", "deterministic", "s-que", "QUE", "", "", "")}
              {step_row("17", "story 4-2 · build", "agent", "liveness · spec checkpoint", "s-que", "QUE", "", "", "")}
              {step_row("…", "stories 4-2 → 4-3", "", "", "s-que", "QUE", "", "", "")}
              {step_row("22", "push", "git", "deterministic", "s-que", "QUE", "", "", "")}
            </tbody></table>
          </div>
        </div>
        <div>
          <div class="sec">
            <div class="sec-h">Stories 5/8</div>
            <div class="strip"><span class="d">1-1</span><span class="d">1-2</span><span class="d">2-1</span><span class="d">3-1</span><span class="d">3-2</span><span class="b">4-1</span><span>4-2</span><span>4-3</span></div>
          </div>
          <div class="sec">
            <div class="sec-h">Artifacts <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">specs/notifications/ · last opened 2d ago</span></div>
            <div class="tree">
              <div>SPEC.md<span class="ts">08-23 18:02</span></div>
              <div>stories.yaml<span class="ts">08-23 18:40</span></div>
              <div>stories/</div>
              <div class="d1">1-1-mattermost-client.md<span class="ts">done</span></div>
              <div class="d1">1-2-project-channel-config.md<span class="ts">done</span></div>
              <div class="d1">2-1-block-event.md<span class="ts">done</span></div>
              <div class="d1">3-1-message-template.md<span class="ts">done</span></div>
              <div class="d1">3-2-retry-on-5xx.md<span class="ts">done</span></div>
              <div class="d1"><span class="new"></span><span class="t1">4-1-mattermost-on-block.md</span><span class="ts amber">blocked</span></div>
            </div>
          </div>
          <div class="sec">
            <div class="sec-h">Cost &amp; trace</div>
            <table class="kv">
              <tr><td>spent / budget</td><td>$9.84 / $40.00</td></tr>
              <tr><td>tokens in / out</td><td>4.1M / 212k</td></tr>
              <tr><td>wall-clock</td><td>2d 06h 29m</td></tr>
              <tr><td>your active time</td><td>11m</td></tr>
              <tr><td>trace</td><td><a>langfuse · wf_01J9Q3K7</a></td></tr>
              <tr><td>branch</td><td><a>github · feat/notifications-mm</a></td></tr>
            </table>
          </div>
          <div class="sec">
            <div class="sec-h">Gate record</div>
            <div class="tree" style="font-size:12px">
              <div><span class="t3">08-24 07:12</span> started by operator · manual estimate 6h</div>
              <div><span class="t3">08-24 09:52</span> story 4-1 blocked · intent gap</div>
            </div>
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
    <div class="bar"><h1>Projects</h1><span class="count">3 projects · 4 repositories</span><span class="spacer"></span><span class="btn pri" data-testid="projects-new">+ New project</span></div>
    <div class="two">
      <div class="list">
        <div class="li on"><span class="ttl">Fullstack App</span><span class="meta">2 repositories · 3 runs · 1 needs you</span></div>
        <div class="li"><span class="ttl">AI Orchestrator</span><span class="meta">1 repository · 3 runs · 1 needs you</span></div>
        <div class="li"><span class="ttl">Website</span><span class="meta">1 repository · 1 run · <span class="red">1 failed</span></span></div>
      </div>
      <div class="dbody" style="padding:20px 28px">
        <div class="dtitle" style="margin:0 0 4px">Fullstack App</div>
        <div class="dmeta" style="margin-bottom:26px">created 2026-08-20 · litellm key <b>fullstack-app</b> · budget this month <b>$61.20 / $300</b></div>
        <div class="sec">
          <div class="sec-h">Context <span class="spacer"></span><span class="ac" style="letter-spacing:0;text-transform:none">edit</span></div>
          <div class="t2" style="font-size:12.5px;line-height:1.65;max-width:760px">Internal operations app for OptimAI: projects, clients, invoices. React 19 + Fastify + Postgres, pnpm monorepo. Strategy: ship weekly, every feature behind a flag. Agents must read <span class="ac">docs/architecture.md</span> and <span class="ac">docs/glossary.md</span> before planning. Never touch <span class="ac">packages/billing</span> without a story that names it.</div>
          <div class="hint">Injected into every agent prompt for this project, before the story. Context files are read from the repository at run time.</div>
        </div>
        <div class="sec">
          <div class="sec-h">Repositories <span class="spacer"></span><span class="btn" style="padding:2px 8px">+ Add repository</span></div>
          <table class="rec"><thead><tr><th style="width:230px">Repository</th><th style="width:90px">Default</th><th style="width:280px">quality_gate_command</th><th style="width:190px">Clone check</th><th>Status</th></tr></thead>
          <tbody>
            <tr><td class="t1">optimai/fullstack-app</td><td>main</td><td>pnpm run check</td><td>ok · 2026-08-25 · 3.2s</td><td>{tok("s-run","RUN")} feat/saved-views · locked</td></tr>
            <tr><td class="t1">optimai/fullstack-infra</td><td>main</td><td class="t3">— none declared</td><td>ok · 2026-08-25 · 1.1s</td><td><span class="t3">idle · verify step will be <b>skipped</b></span></td></tr>
          </tbody></table>
          <div class="hint">Clone check runs <b>git ls-remote</b> then a shallow clone with the project token on save, and again daily. A failing check turns this cell red and blocks new runs on that repository only.</div>
        </div>
        <div class="grid2">
          <div class="sec">
            <div class="sec-h">Credentials</div>
            <table class="kv">
              <tr><td>github token</td><td>set · ghp_…9f2a · scope repo</td></tr>
              <tr><td>litellm virtual key</td><td>set · budget $300 / month</td></tr>
              <tr><td>agent env vars</td><td>3 · <a>show</a></td></tr>
            </table>
            <div class="hint">Scoped to this project. A run for another project can never read these.</div>
          </div>
          <div class="sec">
            <div class="sec-h">Runs on this project</div>
            <table class="kv">
              <tr><td>{tok("s-run","RUN")}</td><td>feat/saved-views · story 3-2</td></tr>
              <tr><td>{tok("s-blk","BLK")}</td><td>feat/notifications-mm · story 4-1</td></tr>
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
    <div class="form" style="display:grid;grid-template-columns:1fr 380px;gap:32px;max-width:none">
      <div>
        {f("Name", '<div class="in">Website</div>')}
        {f("Context", '<div class="in ta">Marketing site, Astro + Tailwind, deployed on Cloudflare Pages. Copy lives in content/*.mdx; never edit generated i18n files. Strategy: SEO first, no client JS unless a story asks for it.</div>', "What every agent reads before planning. Business intent, architecture, hard rules. Plain text; reference files in the repository by path.")}
        {f("Context files", '<div class="in">docs/architecture.md, docs/glossary.md</div>', "Optional. Paths inside the repository, read at run time.")}
        {f("GitHub token", '<div class="in" style="letter-spacing:.2em">••••••••••••••••</div>', "Fine-grained token, <b>repo</b> scope on the repositories below only. Used for clone, push and PR link. Never handed to the agent process.")}
        {f("Agent env vars", '<div class="in ta" style="min-height:44px">NODE_OPTIONS=--max-old-space-size=4096\nPLAYWRIGHT_BROWSERS_PATH=0</div>', "Exported into every agent and shell step for this project.")}
        <div class="sec-h" style="margin-top:26px">Repositories</div>
        <div style="border:1px solid #21272A;padding:4px 14px 12px;margin-bottom:10px">
          {f("URL", '<div class="in">https://github.com/optimai/website</div>')}
          {f("Default branch", '<div class="in" style="width:200px">main</div>')}
          {f("Package manager", '<div class="seg"><span>npm</span><span class="on">pnpm</span><span>yarn</span><span>uv</span><span>other</span></div>')}
          {f("quality_gate_command", '<div class="in">pnpm run check</div>', "Runs after every story as the deterministic gate. Optional — when absent the verify step is <b>skipped</b>, never green.")}
          {f("unit_test_command", '<div class="in ph">optional</div>')}
        </div>
        <span class="btn">+ Another repository</span>
        <div class="actions"><span class="btn pri" data-testid="project-save">Save project</span><span class="btn">Cancel</span><span class="note">The form keeps every value on a failed check.</span></div>
      </div>
      <div>
        <div class="sec-h">Clone check</div>
        <div class="check"><span class="g">ok</span><span>optimai/website · ls-remote · 12 branches</span><span class="t3">0.6s</span></div>
        <div class="check"><span class="g">ok</span><span>optimai/website · shallow clone · 41 MB</span><span class="t3">3.4s</span></div>
        <div class="check"><span class="g">ok</span><span>default branch <span class="ac">main</span> exists</span><span class="t3"></span></div>
        <div class="check"><span class="x">fail</span><span class="t1">optimai/website-cms · clone failed</span><span class="t3">1.9s</span><div class="out">remote: Repository not found.
fatal: Authentication failed for 'https://github.com/optimai/website-cms/'
→ token has no access to this repository. Grant it under GitHub → token → repository access.</div></div>
        <div class="hint" style="margin-top:14px">One failing repository blocks <b>Save project</b> until fixed or removed. The command output is shown verbatim, never summarised.</div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- RUNS (step/task runs)
def run_row(t, proj, wf, step, typ, harness, scls, s, dur, cost, cur=False):
    c = ' class="cur"' if cur else ""
    return f'<tr{c}><td class="t3">{t}</td><td>{proj}</td><td>{wf}</td><td>{step}</td><td>{typ}</td><td>{harness}</td><td>{tok(scls,s)}</td><td class="r">{dur}</td><td class="r">{cost}</td><td><a>trace</a></td></tr>'

RUNS = page("Runs", f'''
<div class="app" data-testid="runs-root">
  {rail("runs")}
  <div class="main">
    <div class="bar">
      <h1>Runs</h1>
      <span class="count">every step, every workflow · 31 today</span>
      <span class="spacer"></span>
      <span class="search">filter…</span>
      <div class="filters"><span class="on">ALL PROJECTS</span><span>FULLSTACK APP</span><span>AI ORCHESTRATOR</span><span>WEBSITE</span></div>
      <div class="filters"><span class="on">ALL</span><span>QUE</span><span>RUN</span><span>BLK</span><span>ERR</span><span>DON</span></div>
    </div>
    <div class="dbody" style="padding:18px 16px 30px">
      <div class="sec">
        <div class="sec-h">Queue <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">dbos queue <b>steps</b> · concurrency 2 · one active run per repository</span></div>
        <table class="rec"><thead><tr><th style="width:40px">Pos</th><th style="width:140px">Project</th><th style="width:200px">Workflow</th><th style="width:200px">Next step</th><th>Waiting because</th><th class="r" style="width:110px">Waiting</th></tr></thead>
        <tbody>
          <tr><td class="t3">1</td><td>Fullstack App</td><td>feat/export-csv</td><td>checkout · git.worktree</td><td>repository <span class="ac">optimai/fullstack-app</span> locked by feat/saved-views</td><td class="r">00h 18m</td></tr>
          <tr><td class="t3">—</td><td>Fullstack App</td><td>feat/notifications-mm</td><td>story 4-1 · build (re-dispatch)</td><td>waiting for your answer · not queued until then</td><td class="r">2d 04h</td></tr>
        </tbody></table>
      </div>
      <div class="sec">
        <div class="sec-h">History <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">newest first · page 1 of 4</span></div>
        <table class="rec"><thead><tr><th style="width:110px">Time</th><th style="width:130px">Project</th><th style="width:180px">Workflow</th><th style="width:170px">Step</th><th style="width:100px">Type</th><th style="width:130px">Harness</th><th style="width:70px">Status</th><th class="r" style="width:70px">Time</th><th class="r" style="width:64px">Cost</th><th style="width:56px"></th></tr></thead>
        <tbody>
          {run_row("09:40:51","Fullstack App","feat/saved-views","story 3-2 · build","agent","claude · sonnet-5","s-run","RUN","42m","$1.90", cur=True)}
          {run_row("09:39:02","AI Orchestrator","feat/board-kanban","story 2-1 · verify","shell","—","s-run","RUN","1m","—", cur=True)}
          {run_row("09:12:44","AI Orchestrator","feat/board-kanban","story 2-1 · build","agent","codex · gpt-5.2-codex","s-don","DON","26m","$1.14")}
          {run_row("08:58:10","Fullstack App","feat/saved-views","story 3-1 · commit","git","—","s-don","DON","2s","—")}
          {run_row("08:57:31","Fullstack App","feat/saved-views","story 3-1 · verify","shell","—","s-don","DON","1m 04s","—")}
          {run_row("08:31:20","Fullstack App","feat/saved-views","story 3-1 · build","agent","claude · sonnet-5","s-don","DON","25m","$1.61")}
          {run_row("06:20:05","AI Orchestrator","feat/auth-token","checkpoint after 1-2","human","—","s-blk","CHK","3h 21m","—")}
          {run_row("06:02:47","AI Orchestrator","feat/auth-token","story 1-2 · build","agent","local · qwen3-coder","s-don","DON","41m","$0.00")}
          {run_row("04:01:12","Website","feat/pricing-page","baseline","shell","—","s-err","ERR","48s","—")}
          {run_row("04:00:58","Website","feat/pricing-page","checkout","git.worktree","—","s-don","DON","6s","—")}
          {run_row("08-24 09:52","Fullstack App","feat/notifications-mm","story 4-1 · build","agent","claude · sonnet-5","s-blk","BLK","22m","$2.10")}
          {run_row("08-24 09:29","Fullstack App","feat/notifications-mm","story 3-2 · verify","shell","—","s-don","DON","57s","—")}
        </tbody></table>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- TEMPLATES
YAML = [
 ('c', '# dev-loop · implement every story in stories.yaml, auto mode'),
 ('k', 'name: <v>dev-loop</v>'), ('k', 'version: <v>3</v>'),
 ('k', 'inputs:'),
 ('k', '  project:        <v>{ type: project }</v>'),
 ('k', '  repository:     <v>{ type: repository }</v>'),
 ('k', '  base_branch:    <v>{ type: string, default: main }</v>'),
 ('k', '  working_branch: <v>{ type: string }</v>'),
 ('k', '  spec_folder:    <v>{ type: path }</v>'),
 ('k', '  epics_file:     <v>{ type: path, required: false }</v>'),
 ('k', '  stories_file:   <v>{ type: path, default: "{{spec_folder}}/stories.yaml" }</v>'),
 ('k', '  harness:        <v>{ type: enum, values: [claude, codex, local], default: claude }</v>'),
 ('k', '  budget_usd:     <v>{ type: number, default: 40 }</v>'),
 ('k', 'steps:'),
 ('k', '  - id: <v>checkout</v>'), ('k', '    run: <s>git.worktree</s>'),
 ('k', '    with: <v>{ branch: "{{working_branch}}", base: "{{base_branch}}" }</v>'),
 ('k', '  - id: <v>baseline</v>'), ('k', '    run: <s>shell</s>'),
 ('k', '    with: <v>{ command: "{{repository.quality_gate_command}}" }</v>'),
 ('k', '    gate: <v>deterministic</v>'), ('k', '    on_fail: <v>escalate</v>'),
 ('k', '  - id: <v>stories</v>'),
 ('k', '    for_each: <v>"{{stories_file}}"</v>'), ('k', '    as: <v>story</v>'),
 ('k', '    steps:'),
 ('k', '      - id: <v>build</v>'), ('k', '        run: <s>agent</s>'),
 ('k', '        with:'),
 ('k', '          harness: <v>"{{harness}}"</v>'),
 ('k', '          skill: <v>bmad-build-auto</v>'),
 ('k', '          args: <v>{ spec_folder: "{{spec_folder}}", story_id: "{{story.id}}" }</v>'),
 ('k', '        output: <v>"{{spec_folder}}/stories/{{story.id}}-*.md"</v>'),
 ('k', '        gate: <v>liveness</v>'),
 ('k', '        escalate_when: <v>output.status in [blocked]</v>'),
 ('k', '        pause_when: <v>story.spec_checkpoint or story.done_checkpoint</v>'),
 ('k', '      - id: <v>verify</v>'), ('k', '        run: <s>shell</s>'),
 ('k', '        with: <v>{ command: "{{repository.quality_gate_command}}" }</v>'),
 ('k', '        gate: <v>deterministic</v>'), ('k', '        on_fail: <v>escalate</v>'),
 ('k', '      - id: <v>commit</v>'), ('k', '        run: <s>git.commit</s>'),
 ('k', '        with: <v>{ paths: ["{{spec_folder}}"], message: "story {{story.id}}: {{story.title}}" }</v>'),
 ('k', '  - id: <v>push</v>'), ('k', '    run: <s>git.push</s>'),
]
def yaml_lines():
    out = []
    for i, (cls, txt) in enumerate(YAML):
        t = txt.replace('<v>', '<span class="v">').replace('</v>', '</span>').replace('<s>', '<span class="s">').replace('</s>', '</span>')
        hl = ' class="hl"' if 32 <= i <= 34 else ''
        out.append(f'<div{hl}><span class="{cls}">{t}</span></div>')
    return "".join(out)

def node(ty, name, gate, cls=""):
    return f'<div class="node {cls}"><span class="ty">{ty}</span><span>{name}</span><span class="gt">{gate}</span></div>'

TEMPLATES = page("Templates", f'''
<div class="app" data-testid="templates-root">
  {rail("templates")}
  <div class="main">
    <div class="bar">
      <h1>Templates</h1>
      <span class="count">dev-loop · v3 · pinned by 4 runs</span>
      <span class="spacer"></span>
      <span class="t3" style="font-size:11px">validated 09:40:12 · no errors</span>
      <span class="btn">Validate</span>
      <span class="btn pri">Save as v4</span>
    </div>
    <div style="display:grid;grid-template-columns:220px 1fr 380px;flex:1;min-height:0">
      <div class="list">
        <div class="li on"><span class="ttl">dev-loop</span><span class="meta">v3 · 4 runs pinned · edited 08-24</span></div>
        <div class="li"><span class="ttl">dev-loop</span><span class="meta">v2 · 1 run pinned · read-only</span></div>
        <div class="li"><span class="ttl">story-only</span><span class="meta">v1 · one story, no loop</span></div>
        <div class="hint" style="padding:12px 14px">A version never changes once a run pins it. Saving creates the next version; running workflows keep theirs.</div>
      </div>
      <div class="code">{yaml_lines()}</div>
      <div style="display:flex;flex-direction:column;min-height:0;overflow:auto">
        <div class="diag">
          <div class="sec-h">Diagram <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">rendered from the yaml · read-only</span></div>
          {node("git", "checkout", "deterministic")}
          <div class="edge"></div>
          {node("shell", "baseline", "deterministic")}
          <div class="edge"></div>
          <div class="loop"><span class="lbl">for each story</span>
            {node("agent", "build · bmad-build-auto", "liveness · pause", "ag")}
            <div class="edge"></div>
            {node("shell", "verify", "deterministic")}
            <div class="edge"></div>
            {node("git", "commit", "—")}
          </div>
          <div class="edge"></div>
          {node("git", "push", "deterministic")}
          <div class="hint" style="margin-top:14px">Teal border = agent step. Amber border = a human gate. escalate edges go to <b>Needs you</b>; they are not drawn.</div>
        </div>
        <div class="diag" style="padding-top:0">
          <div class="sec-h">Inputs bound at start</div>
          <table class="rec"><thead><tr><th>Name</th><th style="width:80px">Type</th><th style="width:110px">Default</th></tr></thead><tbody>
            <tr><td class="t1">project</td><td>project</td><td class="t3">required</td></tr>
            <tr><td class="t1">repository</td><td>repository</td><td class="t3">required</td></tr>
            <tr><td class="t1">base_branch</td><td>string</td><td>main</td></tr>
            <tr><td class="t1">working_branch</td><td>string</td><td class="t3">required</td></tr>
            <tr><td class="t1">spec_folder</td><td>path</td><td class="t3">required</td></tr>
            <tr><td class="t1">epics_file</td><td>path</td><td class="t3">optional</td></tr>
            <tr><td class="t1">stories_file</td><td>path</td><td>{{{{spec_folder}}}}/stories.yaml</td></tr>
            <tr><td class="t1">harness</td><td>enum</td><td>claude</td></tr>
            <tr><td class="t1">budget_usd</td><td>number</td><td>40</td></tr>
          </tbody></table>
        </div>
      </div>
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- USER FLOW
def box(n, title, lines, cls=""):
    return f'''<div style="border:1px solid {'#E4B33C' if cls=='hu' else '#2C3438'};background:#111416;padding:12px 14px;display:flex;flex-direction:column;gap:6px;min-width:0">
  <div style="display:flex;gap:10px;align-items:baseline"><span class="t3" style="font-size:10px;letter-spacing:.18em">{n}</span><span class="t1" style="font-size:12.5px">{title}</span></div>
  <div class="t2" style="font-size:11.5px;line-height:1.6">{lines}</div>
</div>'''

FLOW = page("User workflow", f'''
<div style="width:1440px;height:520px;background:#0B0D0E;padding:26px 28px;display:flex;flex-direction:column;gap:22px">
  <div>
    <div class="sec-h">Operator workflow · v1 · what the human does <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">amber = a screen that asks something of you</span></div>
    <div style="display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px">
      {box("01 · LOGIN", "Enter token", "Once per 30 days.")}
      {box("02 · PROJECTS", "Register project + repositories", "Context text, token, quality_gate_command. Save runs the clone check — a bad token fails here, not hours later.")}
      {box("03 · NEW WORKFLOW", "Bind variables, start", "Template · project · repository · base + working branch · spec folder · epics + stories files · harness. Pre-flight readout. <b>Start run</b>.", "hu")}
      {box("04 · WORKFLOWS", "Walk away, come back", "Board: green = running, amber = needs you, red = failed. Card says which story and step. Nothing else asks for attention.")}
      {box("05 · RUN DETAIL", "Answer, approve, or cancel", "Question at 14px, answer box, or the resume command. Checkpoint: read the story spec, <b>Continue</b>. Rework cap: decide.", "hu")}
      {box("06 · DONE", "Review the branch", "Every story committed, branch pushed, PR link. Cost, trace, gate record. Merge is yours, never the machine's.")}
    </div>
  </div>
  <div>
    <div class="sec-h">What the machine does in between · dev-loop template <span class="spacer"></span><span class="t3" style="letter-spacing:0;text-transform:none">teal = agent · grey = deterministic</span></div>
    <div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:12px;align-items:start">
      {box("STEP", "checkout", "worktree on the working branch, created from base if new")}
      {box("STEP", "baseline", "quality_gate_command on a clean tree. Red before any story = ERR, nothing spent.")}
      <div style="border:1px solid #7FD4C1;background:#111416;padding:12px 14px;display:flex;flex-direction:column;gap:6px"><div style="display:flex;gap:10px"><span class="t3" style="font-size:10px;letter-spacing:.18em">PER STORY</span><span class="t1" style="font-size:12.5px">build</span></div><div class="t2" style="font-size:11.5px;line-height:1.6">bmad-build-auto via claude / codex / local. Writes <b>stories/&lt;id&gt;-*.md</b> with <b>status</b>. <span class="amber">blocked</span> → Needs you. <b>spec_checkpoint</b> → halt after planning.</div></div>
      {box("PER STORY", "verify", "quality_gate_command. Exit ≠ 0 → one retry through the agent, then BLK.")}
      {box("PER STORY", "commit", "spec folder + code. <b>done_checkpoint</b> → CHK, waits for Continue.")}
      {box("STEP", "push", "working branch to origin. PR link on the card.")}
      {box("ALWAYS", "trace + cost", "One Langfuse trace per run; every harness call carries the run id through LiteLLM. Budget breach → BLK.")}
    </div>
  </div>
</div>
''')

# ---------------------------------------------------------------- RUN DIAGRAM
def nd(name, meta, scls, s, cur=False, sub=None, now=False):
    c = " cur" if cur else ""
    subrow = ""
    if sub:
        subrow = '<div class="sub">' + "".join(f'<span class="{"on" if k else ""}">{lbl} {k or "—"}</span>' for lbl, k in sub) + '</div>'
    nowl = ' <span class="now">now</span>' if now else ""
    l2 = f'<div class="l2">{meta}</div>' if meta else ""
    return f'<div class="nd{c}"><div class="l1"><span class="nm">{name}{nowl}</span>{tok(scls, s)}</div>{l2}{subrow}</div>'

def story(id_, title, scls, s, sub, cur=False, now=False):
    return f'<div class="kid">{nd(f"{id_} · {title}", "", scls, s, cur=cur, sub=sub, now=now)}</div>'

D = [("build","done"),("verify","done"),("commit","done")]
Q = [("build",""),("verify",""),("commit","")]
RUNDIAGRAM = page("Run diagram", f"""
<div class="app" data-testid="wfdiag-root">
  {rail("workflows")}
  <div class="main">
    <div class="dhead" style="padding-bottom:12px">
      <div class="crumb"><a>← Workflows</a> · run wf_01J9Q3K7</div>
      <div class="dtitle" style="margin-bottom:6px">{tok("s-blk", "BLK")}<span>feat/notifications-mm</span><span class="t3" style="font-size:12px">blocked 2d 04h</span><span class="spacer"></span><div class="filters"><span class="on">DIAGRAM</span><span>DETAIL</span></div></div>
      <div class="dmeta"><b>Fullstack App</b> · optimai/fullstack-app · base <b>main</b> · spec <b>specs/notifications/</b> · template <b>dev-loop v3</b> · harness <b>claude</b> · started 2026-08-24 07:12</div>
    </div>
    <div class="banner">{tok("s-blk", "BLK")}<span class="msg">Story 4-1 stopped with an intent gap. Switch to DETAIL to answer.</span><span class="go t3">5/8 stories done · $9.84 spent</span></div>
    <div class="heads"><span>Run</span><span>Steps</span><span>Epics</span><span>Stories</span></div>
    <div class="tree">
      <div class="row">
        <div class="nd root"><div class="l1"><span class="nm">feat/notifications-mm</span>{tok("s-blk","BLK")}</div><div class="l2">dev-loop v3 · 5/8 stories · step 15 of 22</div></div>
        <div class="kids">
          <div class="kid">{nd("01 checkout", "git.worktree · 4s", "s-don", "DON")}</div>
          <div class="kid">{nd("02 baseline", "shell · pnpm run check · 1m 12s", "s-don", "DON")}</div>
          <div class="kid"><div class="row">
            {nd("03 stories", "for each · 8 stories · 5 done", "s-blk", "BLK")}
            <div class="kids">
              <div class="kid"><div class="row">{nd("epic 1", "2 stories", "s-don", "DON")}<div class="kids">
                {story("1-1", "mattermost client", "s-don", "DON", D)}
                {story("1-2", "project channel config", "s-don", "DON", D)}
              </div></div></div>
              <div class="kid"><div class="row">{nd("epic 2", "1 story", "s-don", "DON")}<div class="kids">
                {story("2-1", "block event", "s-don", "DON", D)}
              </div></div></div>
              <div class="kid"><div class="row">{nd("epic 3", "2 stories", "s-don", "DON")}<div class="kids">
                {story("3-1", "message template", "s-don", "DON", D)}
                {story("3-2", "retry on 5xx", "s-don", "DON", D)}
              </div></div></div>
              <div class="kid"><div class="row">{nd("epic 4", "3 stories · 1 blocked", "s-blk", "BLK", cur=True)}<div class="kids">
                {story("4-1", "mattermost on block", "s-blk", "BLK", [("build","blocked"),("verify",""),("commit","")], cur=True, now=True)}
                {story("4-2", "operator direct message", "s-que", "QUE", Q)}
                {story("4-3", "silence window", "s-que", "QUE", Q)}
              </div></div></div>
            </div>
          </div></div>
          <div class="kid">{nd("04 push", "git.push · after 8 stories", "s-que", "QUE")}</div>
        </div>
      </div>
    </div>
    <div class="treefoot"><span>step <b>15 of 22</b></span><span>story <b>4-1 · build</b></span><span><b>blocked</b> 2d 04h</span><span><b>5/8</b> stories</span><span class="spacer"></span><span>token = the node's only signal · <b>now</b> marks the current node · QUE = scheduled</span></div>
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
