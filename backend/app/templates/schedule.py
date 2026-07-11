"""Default mini-app template: スケジュール (schedule)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f1f7f4;--card:#fff;--ac:#1f9d6b;--fg:#1d3a30;--mut:#82978e;--bd:#dfeae5;--soft:#e8f5ef;--warn:#d64c4c}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:920px;margin:0 auto;padding:16px;min-height:100vh}
.view{display:block}.view.hidden{display:none}
#detailView{min-height:calc(100vh - 32px)}
h1{font-size:20px;margin:4px 2px 12px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px}
.topbar h1{margin:0}.back{border:1px solid var(--bd);background:#fff;color:var(--ac);border-radius:10px;padding:9px 12px;font-weight:800;cursor:pointer}
.add{display:grid;grid-template-columns:auto auto 1fr auto;gap:8px}
.add input,.detail input,.detail textarea{padding:10px;border:1px solid var(--bd);border-radius:10px;font-size:14px;min-width:0;background:#fff;color:var(--fg)}
.add button{padding:0 16px;border:0;background:var(--ac);color:#fff;border-radius:10px;font-weight:700;cursor:pointer}
@media(max-width:600px){.add{grid-template-columns:1fr 1fr}.add .ti{grid-column:span 2}.add button{grid-column:span 2}}
.calbox{margin-top:16px;background:var(--card);border:1px solid var(--bd);border-radius:14px;overflow:hidden}
.calhead{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px;background:var(--soft)}
.calhead button,.detail button{border:0;border-radius:10px;padding:9px 12px;font-weight:700;cursor:pointer}
.calhead button{background:#fff;color:var(--ac);border:1px solid var(--bd)}
.month{font-weight:800;font-size:16px}
.week,.grid{display:grid;grid-template-columns:repeat(7,1fr)}
.week div{padding:8px;text-align:center;color:var(--mut);font-size:12px;font-weight:700;border-bottom:1px solid var(--bd)}
.cell{min-height:108px;border-right:1px solid var(--bd);border-bottom:1px solid var(--bd);padding:7px;background:#fff;cursor:pointer}
.cell:nth-child(7n){border-right:0}
.cell.out{background:#f8fbf9;color:#b7c4be}
.cell.today .num{background:var(--ac);color:#fff}
.num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:999px;font-size:12px;font-weight:800}
.events{display:flex;flex-direction:column;gap:4px;margin-top:4px}
.chip{border:0;text-align:left;border-radius:7px;background:#e7f3ff;color:#18334b;padding:4px 6px;font-size:12px;line-height:1.25;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip .time{font-weight:800;color:var(--ac);margin-right:4px}
.more{font-size:11px;color:var(--mut);padding-left:2px}
.detail{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:14px;min-height:calc(100vh - 86px);display:grid;grid-template-rows:auto minmax(220px,1fr) auto;gap:10px}
.detail h2{font-size:16px;margin:0 0 10px;color:var(--ac)}
.detailgrid{display:grid;grid-template-columns:minmax(140px,180px) minmax(96px,120px) minmax(220px,1fr);gap:8px;align-items:end}
.memowrap{display:grid;grid-template-rows:auto minmax(180px,1fr) auto;gap:5px;min-height:0}.detail label{display:grid;gap:5px;font-size:12px;color:var(--mut);font-weight:700}
.detail textarea{height:100%;min-height:0;resize:none;line-height:1.55}
.links{display:flex;flex-wrap:wrap;gap:6px;min-height:0}.linkbtn{border:1px solid #b9d8cb!important;background:#f3fbf7;color:#156447;border-radius:999px;padding:6px 10px;font-size:12px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.actions{display:flex;gap:8px;justify-content:flex-end}.save{background:var(--ac);color:#fff}.delete{background:#fff;color:var(--warn);border:1px solid #f0c9c9!important}.close{background:#eef3f0;color:var(--fg)}
.empty{color:#aab;text-align:center;padding:14px}
@media(max-width:700px){.wrap{padding:10px;min-height:100vh}#detailView{min-height:calc(100vh - 20px)}.cell{min-height:86px;padding:5px}.chip{font-size:11px}.detail{min-height:calc(100vh - 74px)}.detailgrid{grid-template-columns:1fr 1fr}.detailgrid .titlefield{grid-column:1/-1}.week div{font-size:11px;padding:6px 2px}}
</style></head><body>
<div class="wrap">
  <div id="calendarView" class="view">
    <h1>🗓 スケジュール</h1>
    <div class="add">
      <input id="d" type="date"><input id="t" type="time">
      <input id="ti" class="ti" placeholder="予定（例：歯医者）"><button id="addb">追加</button>
    </div>
    <div class="calbox">
      <div class="calhead"><button id="prev">前月</button><div id="month" class="month"></div><button id="next">翌月</button></div>
      <div class="week"><div>日</div><div>月</div><div>火</div><div>水</div><div>木</div><div>金</div><div>土</div></div>
      <div id="grid" class="grid"></div>
    </div>
  </div>
  <div id="detailView" class="view hidden">
    <div class="topbar"><button id="backb" class="back">カレンダーへ戻る</button><h1>予定の詳細</h1></div>
    <div id="detail" class="detail">
      <div class="detailgrid">
        <label>日付<input id="ed" type="date"></label>
        <label>時刻<input id="et" type="time"></label>
        <label class="titlefield">タイトル<input id="eti" placeholder="予定のタイトル"></label>
      </div>
      <label class="memowrap">メモ<textarea id="em" placeholder="持ち物、場所、補足など"></textarea><span id="links" class="links"></span></label>
      <div class="actions"><button id="delb" class="delete">削除</button><button id="closeb" class="close">閉じる</button><button id="saveb" class="save">保存</button></div>
    </div>
  </div>
</div>
<script>
(function(){
  var evs=[],shown=new Date(),selected=null,draftDate='',grid=document.getElementById('grid'),monthEl=document.getElementById('month');
  var dEl=document.getElementById('d'),tEl=document.getElementById('t'),tiEl=document.getElementById('ti');
  var calendarView=document.getElementById('calendarView'),detailView=document.getElementById('detailView');
  var detail=document.getElementById('detail'),ed=document.getElementById('ed'),et=document.getElementById('et'),eti=document.getElementById('eti'),em=document.getElementById('em'),linksEl=document.getElementById('links');
  function save(){AF.save({events:evs});}
  function uid(){return 'e'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);}
  function iso(dt){return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0');}
  function sameMonth(a,b){return a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth();}
  function sortEvents(a,b){return (a.time||'99:99').localeCompare(b.time||'99:99')||a.title.localeCompare(b.title);}
  function byId(id){return evs.filter(function(e){return e.id===id;})[0]||null;}
  function fmtTitle(e){return (e.time?e.time+' ':'')+e.title;}
  function render(){
    grid.innerHTML='';monthEl.textContent=shown.getFullYear()+'年 '+(shown.getMonth()+1)+'月';
    var first=new Date(shown.getFullYear(),shown.getMonth(),1),start=new Date(first);start.setDate(first.getDate()-first.getDay());
    var today=iso(new Date());
    for(var i=0;i<42;i++){
      var day=new Date(start);day.setDate(start.getDate()+i);var ds=iso(day);
      var cell=document.createElement('div');cell.className='cell'+(sameMonth(day,shown)?'':' out')+(ds===today?' today':'');
      cell.onclick=function(date){return function(e){if(e.target.closest&&e.target.closest('.chip'))return;openNewDetail(date);};}(ds);
      var num=document.createElement('span');num.className='num';num.textContent=String(day.getDate());cell.appendChild(num);
      var wrap=document.createElement('div');wrap.className='events';
      var dayEvents=evs.filter(function(e){return e.date===ds;}).sort(sortEvents);
      dayEvents.slice(0,3).forEach(function(e){
        var b=document.createElement('button');b.className='chip';b.title=fmtTitle(e);
        b.innerHTML=(e.time?'<span class="time">'+e.time+'</span>':'')+escapeHtml(e.title);
        b.onclick=function(id){return function(evt){evt.stopPropagation();openDetail(id);};}(e.id);
        wrap.appendChild(b);
      });
      if(dayEvents.length>3){var more=document.createElement('div');more.className='more';more.textContent='+'+(dayEvents.length-3)+'件';wrap.appendChild(more);}
      cell.appendChild(wrap);grid.appendChild(cell);
    }
  }
  function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function validUrl(url){try{var u=new URL(url);return u.protocol==='https:'||u.protocol==='http:';}catch(e){return false;}}
  function renderLinks(){linksEl.replaceChildren();var seen={};var matches=(em.value||'').match(/https?:\/\/[^\s<>"')]+/g)||[];matches.slice(0,12).forEach(function(raw){var url=raw.replace(/[.,、。]+$/,'');if(seen[url]||!validUrl(url))return;seen[url]=true;var b=document.createElement('button');b.type='button';b.className='linkbtn';b.textContent=url;b.title=url;b.onclick=function(evt){evt.preventDefault();if(window.AF&&AF.openExternal)AF.openExternal(url);};linksEl.appendChild(b);});}
  function add(date,time,title,memo){title=(title||'').trim();if(!date||!title)return;evs.push({id:uid(),date:date,time:time||'',title:title,memo:memo||''});shown=new Date(date+'T00:00');save();render();}
  function showDetail(){calendarView.classList.add('hidden');detailView.classList.remove('hidden');scrollTo(0,0);}
  function openNewDetail(date){selected=null;draftDate=date;ed.value=date;et.value='';eti.value='';em.value='';renderLinks();if(window.AF&&AF.setChatContext)AF.setChatContext('new_'+date,date+' の新規予定');showDetail();}
  function openDetail(id){var e=byId(id);if(!e)return;selected=id;draftDate='';ed.value=e.date||'';et.value=e.time||'';eti.value=e.title||'';em.value=e.memo||'';renderLinks();if(window.AF&&AF.setChatContext)AF.setChatContext('event_'+e.id,(e.title||'予定')+' のメモ');showDetail();}
  function closeDetail(){selected=null;draftDate='';if(window.AF&&AF.setChatContext)AF.setChatContext('default','スケジュール');detailView.classList.add('hidden');calendarView.classList.remove('hidden');scrollTo(0,0);}
  function updateSelected(){var e=byId(selected);if(!e){e={id:uid(),date:ed.value||draftDate||iso(new Date()),time:'',title:'無題',memo:''};evs.push(e);selected=e.id;}e.date=ed.value;e.time=et.value;e.title=(eti.value||'').trim()||'無題';e.memo=em.value||'';shown=new Date((e.date||iso(new Date()))+'T00:00');save();render();openDetail(e.id);}
  function deleteSelected(){if(!selected){closeDetail();return;}evs=evs.filter(function(e){return e.id!==selected;});closeDetail();save();render();}
  document.getElementById('addb').onclick=function(){add(dEl.value,tEl.value,tiEl.value);tiEl.value='';};
  tiEl.addEventListener('keydown',function(e){if(e.key==='Enter'){add(dEl.value,tEl.value,tiEl.value);tiEl.value='';}});
  document.getElementById('prev').onclick=function(){shown.setMonth(shown.getMonth()-1);render();};
  document.getElementById('next').onclick=function(){shown.setMonth(shown.getMonth()+1);render();};
  document.getElementById('saveb').onclick=updateSelected;document.getElementById('delb').onclick=deleteSelected;document.getElementById('closeb').onclick=closeDetail;document.getElementById('backb').onclick=closeDetail;
  em.addEventListener('input',renderLinks);
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_event'){add(args.date,args.time,args.title,args.memo);}
    else if(name==='update_event'){evs.forEach(function(x){if((args.id&&x.id===args.id)||(!args.id&&x.title===args.title&&(!args.date||x.date===args.date))){if(args.new_date)x.date=args.new_date;if(args.time!==undefined)x.time=args.time||'';if(args.new_title)x.title=args.new_title;if(args.memo!==undefined)x.memo=args.memo||'';}});save();render();}
    else if(name==='delete_event'){evs=evs.filter(function(x){if(args.all&&args.date)return x.date!==args.date;if(args.all&&!args.date)return false;return !(x.title===args.title&&(!args.date||x.date===args.date));});save();render();}
    else if(name==='update_event_memo'){evs.forEach(function(x){if((args.id&&x.id===args.id)||(!args.id&&x.title===args.title&&(!args.date||x.date===args.date))){x.memo=args.memo||'';}});save();render();}
  };
  (async function(){var s=await AF.load();if(s&&Array.isArray(s.events))evs=s.events;
    var n=new Date();dEl.value=iso(n);shown=new Date(n.getFullYear(),n.getMonth(),1);render();})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "schedule",
    "title": "スケジュール",
    "description": "日付・時刻つきの予定を月カレンダーに登録し、予定詳細にメモも残せます。内容は自動保存されます。",
    "kind": "app",
    "theme": "forest",
    "html": _HTML,
    "commands": [
        {"name": "add_event", "description": "予定を追加（date=YYYY-MM-DD, time=HH:MM 任意, memo 任意）",
         "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}, "time": {"type": "string"}, "title": {"type": "string"}, "memo": {"type": "string"}}, "required": ["date", "title"]}},
        {"name": "delete_event", "description": "予定を削除（title一致、date任意で絞り込み。date + all=true でその日の予定を一括削除）",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "date": {"type": "string"}, "all": {"type": "boolean"}}, "required": []}},
        {"name": "update_event", "description": "予定を更新（title/dateで対象を探し、new_date/time/new_title/memoを反映）",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "date": {"type": "string"}, "new_date": {"type": "string"}, "time": {"type": "string"}, "new_title": {"type": "string"}, "memo": {"type": "string"}}, "required": ["title"]}},
        {"name": "update_event_memo", "description": "予定のメモを更新（id優先。title一致、date任意で絞り込み）",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "date": {"type": "string"}, "memo": {"type": "string"}}, "required": ["memo"]}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "description": "カレンダーに表示する予定一覧",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "time": {"type": "string", "description": "HH:MM。終日なら空文字"},
                        "title": {"type": "string"},
                        "memo": {"type": "string"},
                    },
                    "required": ["id", "date", "title"],
                },
            }
        },
        "required": ["events"],
    },
    "worker_instructions": (
        "スケジュール操作用ワーカー。予定の追加、削除、日付/時刻/タイトル/メモ変更を担当する。"
        "『入れて/追加/登録』は add_event、『消して/削除/すべて消して』は delete_event、"
        "『変更/移動/リネーム』は update_event、『メモして/メモを変えて』は update_event_memo。"
        "依頼は実行前に date/time/title/memo へ構造化する。"
        "『予定に出張を入れて』の予定名は『出張』であり、title に『予定』『入れて』などの依頼語を残さない。"
        "予定追加とメモ用の調査が一つの依頼にある場合は、予定と調査済みメモに分けて一度に保存する。"
        "『メモに〜を記入して/書いて/追記して』『〜を探してメモに入れて』、"
        "および予定詳細を開いている文脈での『候補を記入して/結果を書いて/情報を追記して』は、"
        "予定本文の更新として扱い、必要なら短い実用的なメモ文を作って update_event_memo へ渡す。"
        "断片的なメモ依頼はそのまま転記せず、『持っていくもの: ノート』『確認事項: 集合時間』のように整理して記入する。"
        "日付だけで『予定を全部消して』なら delete_event に date と all=true を渡す。"
        "時刻が15:65のように不自然なら実行せず、16:05の意味か確認する。"
        "対象予定が特定できない更新/削除は、タイトルや日付を聞き返す。"
    ),
    "worker_examples": [
        {"user": "7月13日の予定に出張をいれて。メモに仙台駅近くのラーメン屋を3件調べて記入して", "command": {"name": "add_event", "arguments": {"date": "YYYY-07-13", "time": "", "title": "出張", "memo": "調査済みのラーメン店3件を店名・要点・リンク付きで記入"}}, "reply": "「出張」を追加し、調査結果をメモに記入します。"},
        {"user": "22日の15時に歯医者を入れて", "command": {"name": "add_event", "arguments": {"date": "YYYY-MM-22", "time": "15:00", "title": "歯医者", "memo": ""}}, "reply": "予定を追加します。"},
        {"user": "22日の予定をすべて消して", "command": {"name": "delete_event", "arguments": {"date": "YYYY-MM-22", "all": True}}, "reply": "その日の予定をすべて削除します。"},
        {"user": "歯医者を16時に変更して", "command": {"name": "update_event", "arguments": {"title": "歯医者", "time": "16:00"}}, "reply": "予定の時刻を変更します。"},
        {"user": "仙台出張のメモに仙台駅近くの仙台名物の食事処を3つ探して記入して", "command": {"name": "update_event_memo", "arguments": {"title": "仙台出張", "memo": "仙台駅周辺の食事候補を3件、営業時間確認付きで記入する"}}, "reply": "予定のメモを更新します。"},
        {"user": "仙台駅から徒歩圏内で仙台の名物料理が食べられるレストランを探して3件候補を記入して", "command": {"name": "update_event_memo", "arguments": {"title": "現在開いている予定", "memo": "仙台駅徒歩圏の食事候補を3件、確認事項付きで記入する"}}, "reply": "候補を調べて予定のメモを更新します。"},
        {"user": "メモに持っていくものとしてノートを追記して", "command": {"name": "update_event_memo", "arguments": {"title": "現在開いている予定", "memo": "持っていくもの: ノート"}}, "reply": "予定のメモに整理して追記します。"},
        {"user": "15:65にテストを入れて", "command": {"name": "", "arguments": {}}, "reply": "15:65は時刻として不自然です。16:05の意味でよろしいですか？"},
    ],
}
