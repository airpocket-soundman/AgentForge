"""Default mini-app template: スケジュール (schedule)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f1f7f4;--card:#fff;--ac:#1f9d6b;--fg:#1d3a30;--mut:#82978e;--bd:#dfeae5}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:680px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 2px 12px}
.add{display:grid;grid-template-columns:auto auto 1fr auto;gap:8px}
.add input{padding:10px;border:1px solid var(--bd);border-radius:10px;font-size:14px;min-width:0}
.add button{padding:0 16px;border:0;background:var(--ac);color:#fff;border-radius:10px;font-weight:700;cursor:pointer}
@media(max-width:600px){.add{grid-template-columns:1fr 1fr}.add .ti{grid-column:span 2}.add button{grid-column:span 2}}
.day{margin-top:16px}
.day h2{font-size:14px;color:var(--ac);margin:0 0 6px;border-bottom:2px solid var(--bd);padding-bottom:4px}
.ev{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;margin-bottom:6px}
.tm{font-variant-numeric:tabular-nums;font-weight:700;color:var(--ac);flex:0 0 56px}
.tt{flex:1;word-break:break-word}
.del{border:0;background:transparent;color:var(--mut);font-size:18px;cursor:pointer}
.empty{color:#aab;text-align:center;padding:30px}
</style></head><body>
<div class="wrap">
  <h1>🗓 スケジュール</h1>
  <div class="add">
    <input id="d" type="date"><input id="t" type="time">
    <input id="ti" class="ti" placeholder="予定（例：歯医者）"><button id="addb">追加</button>
  </div>
  <div id="list"></div>
</div>
<script>
(function(){
  var evs=[],list=document.getElementById('list');
  var dEl=document.getElementById('d'),tEl=document.getElementById('t'),tiEl=document.getElementById('ti');
  function save(){AF.save({events:evs});}
  function uid(){return 'e'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);}
  function fmtDate(d){try{var x=new Date(d+'T00:00');return (x.getMonth()+1)+'月'+x.getDate()+'日('+'日月火水木金土'[x.getDay()]+')';}catch(_){return d;}}
  function render(){
    list.innerHTML='';
    if(!evs.length){list.innerHTML='<div class="empty">予定はありません</div>';return;}
    var by={};evs.forEach(function(e){(by[e.date]=by[e.date]||[]).push(e);});
    Object.keys(by).sort().forEach(function(dt){
      var sec=document.createElement('div');sec.className='day';
      var h=document.createElement('h2');h.textContent=fmtDate(dt);sec.appendChild(h);
      by[dt].sort(function(a,b){return (a.time||'').localeCompare(b.time||'');}).forEach(function(e){
        var row=document.createElement('div');row.className='ev';
        var tm=document.createElement('div');tm.className='tm';tm.textContent=e.time||'終日';
        var tt=document.createElement('div');tt.className='tt';tt.textContent=e.title;
        var del=document.createElement('button');del.className='del';del.textContent='×';del.onclick=function(){evs=evs.filter(function(x){return x.id!==e.id;});save();render();};
        row.appendChild(tm);row.appendChild(tt);row.appendChild(del);sec.appendChild(row);
      });
      list.appendChild(sec);
    });
  }
  function add(date,time,title){title=(title||'').trim();if(!date||!title)return;evs.push({id:uid(),date:date,time:time||'',title:title});save();render();}
  document.getElementById('addb').onclick=function(){add(dEl.value,tEl.value,tiEl.value);tiEl.value='';};
  tiEl.addEventListener('keydown',function(e){if(e.key==='Enter'){add(dEl.value,tEl.value,tiEl.value);tiEl.value='';}});
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_event'){add(args.date,args.time,args.title);}
    else if(name==='delete_event'){evs=evs.filter(function(x){return !(x.title===args.title&&(!args.date||x.date===args.date));});save();render();}
  };
  (async function(){var s=await AF.load();if(s&&Array.isArray(s.events))evs=s.events;
    var n=new Date();dEl.value=n.toISOString().slice(0,10);render();})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "schedule",
    "title": "スケジュール",
    "description": "日付・時刻つきの予定を登録し、日付ごとに時系列で表示します。内容は自動保存されます。",
    "kind": "app",
    "theme": "forest",
    "html": _HTML,
    "commands": [
        {"name": "add_event", "description": "予定を追加（date=YYYY-MM-DD, time=HH:MM 任意）",
         "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}, "time": {"type": "string"}, "title": {"type": "string"}}, "required": ["date", "title"]}},
        {"name": "delete_event", "description": "予定を削除（title一致、date任意で絞り込み）",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "date": {"type": "string"}}, "required": ["title"]}},
    ],
}
