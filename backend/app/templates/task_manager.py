"""Default mini-app template: タスク管理 (task_manager)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f4f6fb;--card:#fff;--ac:#4a7dff;--fg:#1f2545;--mut:#8a90ad;--done:#9aa0bd;--bd:#e7eaf3;--soft:#eef2ff;--warn:#d95555}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:760px;margin:0 auto;padding:16px;min-height:100%;display:flex;flex-direction:column}
.screen{display:none;min-height:0;flex:1}.screen.on{display:flex;flex-direction:column}
.head{display:flex;align-items:center;gap:10px;margin:4px 2px 12px}.head h1{font-size:20px;margin:0}.spacer{flex:1}
.back,.small{border:1px solid var(--bd);background:#fff;color:var(--fg);border-radius:10px;padding:8px 11px;font-weight:700;cursor:pointer}
.add{display:flex;gap:8px}
.add input{flex:1;padding:12px;border:1px solid var(--bd);border-radius:10px;font-size:15px;background:#fff;color:var(--fg);min-width:0}
.add button,.primary{padding:0 18px;border:0;background:var(--ac);color:#fff;border-radius:10px;font-weight:700;cursor:pointer}
.filters{display:flex;gap:6px;margin:12px 2px 4px}
.filters button{border:1px solid var(--bd);background:#fff;border-radius:20px;padding:5px 12px;font-size:13px;color:var(--mut);cursor:pointer}
.filters button.on{background:var(--ac);color:#fff;border-color:var(--ac)}
ul{list-style:none;margin:8px 0;padding:0;flex:1}
li{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:11px 12px;margin-bottom:8px;cursor:pointer}
li:hover{border-color:#c9d2ff;box-shadow:0 6px 16px rgba(40,56,120,.08)}
li.done .t{text-decoration:line-through;color:var(--done)}
.ck{width:22px;height:22px;border-radius:50%;border:2px solid var(--ac);flex:0 0 auto;cursor:pointer;display:grid;place-items:center;color:#fff;font-size:13px}
li.done .ck{background:var(--ac)}
.t{flex:1;font-size:15px;word-break:break-word}
.del{border:0;background:transparent;color:var(--mut);font-size:18px;cursor:pointer;padding:4px}
.empty{color:#aab;text-align:center;padding:30px}.foot{color:var(--mut);font-size:13px;padding:6px 2px}
.detail-card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px;min-height:220px;overflow:auto}
.detail-title{font-size:20px;margin:0 0 6px;word-break:break-word}.detail-meta{display:flex;gap:10px;align-items:center;color:var(--mut);font-size:13px;margin-bottom:14px}
.badge{display:inline-flex;align-items:center;border-radius:999px;padding:3px 9px;background:var(--soft);color:var(--ac);font-weight:800;font-size:12px}
.detail-html{line-height:1.75}.detail-html h2,.detail-html h3{margin:1em 0 .4em}.detail-html p{margin:.6em 0}.detail-html ul,.detail-html ol{padding-left:1.3em}.detail-html code{background:#f1f3f7;border-radius:6px;padding:2px 5px}.detail-html blockquote{margin:10px 0;padding:8px 12px;border-left:4px solid var(--ac);background:#f8f9ff;color:#505678}
.guide{margin-top:12px;border:1px dashed #cbd2e8;border-radius:12px;background:#fbfcff;color:#68708f;padding:12px;font-size:13px;line-height:1.7}
.actions{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}.danger{color:var(--warn)}
@media(max-width:640px){.wrap{padding:10px}.add{flex-direction:column}.add button{min-height:42px}.head{align-items:flex-start}.actions{flex-wrap:wrap}.small,.back{padding:8px 10px}}
</style></head><body>
<div class="wrap">
  <section id="listScreen" class="screen on">
    <div class="head"><h1>📋 タスク管理</h1></div>
    <div class="add"><input id="inp" placeholder="やることを入力してEnter…"><button id="addb">追加</button></div>
    <div class="filters"><button data-f="all" class="on">すべて</button><button data-f="active">未完了</button><button data-f="done">完了</button></div>
    <ul id="list"></ul>
    <div class="foot" id="foot"></div>
  </section>
  <section id="detailScreen" class="screen">
    <div class="head">
      <button id="backb" class="back">← 一覧</button>
      <h1 id="detailTitle" class="detail-title"></h1>
      <span class="spacer"></span>
      <button id="detailDone" class="small"></button>
    </div>
    <div class="detail-meta"><span id="detailState" class="badge"></span><span id="detailHint"></span></div>
    <article class="detail-card"><div id="detailHtml" class="detail-html"></div></article>
    <div class="guide">詳細内容は下のアプリチャットでワーカーに依頼して編集します。例: 「このタスクの詳細に手順を3つ書いて」「注意点を追記して」「HTMLで見出し付きに整えて」。</div>
    <div class="actions"><button id="detailDelete" class="small danger">削除</button></div>
  </section>
</div>
<script>
(function(){
  var tasks=[],filter='all',selected=null;
  var inp=document.getElementById('inp'),list=document.getElementById('list'),foot=document.getElementById('foot');
  var listScreen=document.getElementById('listScreen'),detailScreen=document.getElementById('detailScreen'),detailTitle=document.getElementById('detailTitle');
  var detailHtml=document.getElementById('detailHtml'),detailState=document.getElementById('detailState'),detailHint=document.getElementById('detailHint'),detailDone=document.getElementById('detailDone');
  function state(){return {tasks:tasks,selected_task_id:selected};}
  function save(){AF.save(state());}
  function uid(){return 't'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);}
  function byId(id){return tasks.filter(function(t){return t.id===id;})[0]||null;}
  function byTitle(title){title=String(title||'').trim();return tasks.filter(function(t){return t.title===title;})[0]||null;}
  function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function defaultHtml(title){return '<h2>'+escapeHtml(title)+'</h2><p>このタスクの詳細はまだありません。</p>';}
  function sanitize(html){
    var tpl=document.createElement('template');tpl.innerHTML=String(html||'');
    var allowed={H2:1,H3:1,H4:1,P:1,UL:1,OL:1,LI:1,STRONG:1,EM:1,B:1,I:1,U:1,CODE:1,PRE:1,BLOCKQUOTE:1,BR:1,HR:1,SPAN:1,DIV:1};
    Array.prototype.slice.call(tpl.content.querySelectorAll('*')).forEach(function(el){
      if(!allowed[el.tagName]){el.replaceWith(document.createTextNode(el.textContent||''));return;}
      Array.prototype.slice.call(el.attributes).forEach(function(a){
        var n=a.name.toLowerCase(),v=a.value||'';
        if(n.indexOf('on')===0||n==='style'||n==='src'||n==='srcdoc'){el.removeAttribute(a.name);return;}
        if(n!=='class')el.removeAttribute(a.name);
      });
    });
    return tpl.innerHTML;
  }
  function normalize(){
    tasks=tasks.map(function(t){
      return {id:String(t.id||uid()),title:String(t.title||'無題'),done:!!t.done,detail_html:String(t.detail_html||t.detailHtml||defaultHtml(t.title||'無題'))};
    });
  }
  function setContext(id,label){try{AF.setChatContext(id,label);}catch(_){}}
  function showList(persist){
    selected=null;listScreen.classList.add('on');detailScreen.classList.remove('on');setContext('list','タスク一覧');renderList();
    if(persist)save();
  }
  function openDetail(id,persist){
    var t=byId(id);if(!t)return;selected=id;listScreen.classList.remove('on');detailScreen.classList.add('on');
    detailTitle.textContent=t.title;detailState.textContent=t.done?'完了':'未完了';detailHint.textContent='この画面の内容はHTMLとして保存・表示されます。';
    detailDone.textContent=t.done?'未完了に戻す':'完了にする';detailHtml.innerHTML=sanitize(t.detail_html||defaultHtml(t.title));
    setContext('task_'+t.id,'詳細: '+t.title);
    if(persist)save();
  }
  function renderList(){
    var shown=tasks.filter(function(t){return filter==='all'||(filter==='done')===!!t.done;});
    list.innerHTML='';
    if(!shown.length){var d=document.createElement('div');d.className='empty';d.textContent='タスクはありません';list.appendChild(d);}
    shown.forEach(function(t){
      var li=document.createElement('li');if(t.done)li.className='done';li.onclick=function(){openDetail(t.id,true);};
      var ck=document.createElement('div');ck.className='ck';ck.textContent=t.done?'✓':'';ck.onclick=function(e){e.stopPropagation();t.done=!t.done;save();renderList();};
      var sp=document.createElement('div');sp.className='t';sp.textContent=t.title;
      var del=document.createElement('button');del.className='del';del.textContent='×';del.onclick=function(e){e.stopPropagation();tasks=tasks.filter(function(x){return x.id!==t.id;});save();renderList();};
      li.appendChild(ck);li.appendChild(sp);li.appendChild(del);list.appendChild(li);
    });
    var left=tasks.filter(function(t){return !t.done;}).length;
    foot.textContent=tasks.length?(left+' 件 未完了 / 全 '+tasks.length+' 件'):'';
  }
  function add(title,detailHtmlValue){title=(title||'').trim();if(!title)return;tasks.push({id:uid(),title:title,done:false,detail_html:detailHtmlValue||defaultHtml(title)});save();renderList();}
  function selectedTask(){return byId(selected);}
  function updateDetail(target,html,append){
    var t=target&&target.id?byId(target.id):byTitle(target&&target.title);if(!t&&selected)t=selectedTask();if(!t)return false;
    t.detail_html=append?(String(t.detail_html||'')+String(html||'')):String(html||'');
    if(!t.detail_html.trim())t.detail_html=defaultHtml(t.title);save();if(selected===t.id)openDetail(t.id,false);else renderList();return true;
  }
  document.getElementById('addb').onclick=function(){add(inp.value);inp.value='';inp.focus();};
  inp.addEventListener('keydown',function(e){if(e.key==='Enter'){add(inp.value);inp.value='';}});
  document.getElementById('backb').onclick=function(){showList(true);};
  detailDone.onclick=function(){var t=selectedTask();if(!t)return;t.done=!t.done;save();openDetail(t.id,false);};
  document.getElementById('detailDelete').onclick=function(){if(!selected)return;tasks=tasks.filter(function(x){return x.id!==selected;});save();showList(true);};
  document.querySelectorAll('.filters button').forEach(function(b){b.onclick=function(){
    filter=b.getAttribute('data-f');document.querySelectorAll('.filters button').forEach(function(x){x.classList.remove('on');});b.classList.add('on');renderList();};});
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_task'){add(args.title,args.detail_html);}
    else if(name==='toggle_task'){var t=byTitle(args.title)||(args.id?byId(args.id):null);if(t){t.done=args.done!==undefined?!!args.done:!t.done;save();selected===t.id?openDetail(t.id,false):renderList();}}
    else if(name==='rename_task'){var r=byTitle(args.title)||(args.id?byId(args.id):null);if(r&&args.new_title){r.title=args.new_title;save();selected===r.id?openDetail(r.id,false):renderList();}}
    else if(name==='delete_task'){tasks=tasks.filter(function(x){return !((args.id&&x.id===args.id)||(!args.id&&x.title===args.title));});save();if(args.id&&selected===args.id)showList(true);else renderList();}
    else if(name==='clear_done'){tasks=tasks.filter(function(x){return !x.done;});save();if(selected&&!byId(selected))showList(true);else renderList();}
    else if(name==='update_task_detail_html'){updateDetail(args,args.detail_html||args.html||'',false);}
    else if(name==='append_task_detail_html'){updateDetail(args,args.detail_html||args.html||'',true);}
    else if(name==='open_task_detail'){var o=byTitle(args.title)||(args.id?byId(args.id):null);if(o)openDetail(o.id,true);}
  };
  (async function(){var s=await AF.load();if(s&&Array.isArray(s.tasks))tasks=s.tasks;normalize();if(s&&s.selected_task_id&&byId(s.selected_task_id))openDetail(s.selected_task_id,false);else showList(false);})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "task_manager",
    "title": "タスク管理",
    "description": "タスク一覧から詳細画面へ移動でき、詳細内容をHTMLとして保存・レンダリングするToDo。詳細編集はアプリのワーカーに依頼します。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "add_task", "description": "タスクを追加。detail_htmlで初期詳細HTMLも設定可能",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "detail_html": {"type": "string"}}, "required": ["title"]}},
        {"name": "toggle_task", "description": "完了/未完了を切替（done省略でトグル）",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "done": {"type": "boolean"}}, "required": []}},
        {"name": "rename_task", "description": "タスク名を変更",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "new_title": {"type": "string"}}, "required": ["new_title"]}},
        {"name": "delete_task", "description": "タスクを削除",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}}, "required": []}},
        {"name": "clear_done", "description": "完了タスクを一括削除", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "update_task_detail_html", "description": "タスク詳細HTMLを置き換える。HTMLは本文断片（h2/p/ul等）で指定",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "detail_html": {"type": "string"}}, "required": ["detail_html"]}},
        {"name": "append_task_detail_html", "description": "タスク詳細HTMLへ追記する。HTMLは本文断片（h2/p/ul等）で指定",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}, "detail_html": {"type": "string"}}, "required": ["detail_html"]}},
        {"name": "open_task_detail", "description": "指定タスクの詳細画面を開く",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}}, "required": []}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "タスク一覧。詳細画面は各タスクの detail_html をHTMLとしてレンダリングする",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "done": {"type": "boolean"},
                        "detail_html": {
                            "type": "string",
                            "description": "タスク詳細のHTML本文断片。ユーザーは直接編集せず、Specialist Workerが依頼に応じて編集する",
                        },
                    },
                    "required": ["id", "title", "done", "detail_html"],
                },
            },
            "selected_task_id": {
                "type": ["string", "null"],
                "description": "現在開いている詳細画面のタスクID。一覧画面ではnull。詳細編集後も同じ詳細画面に留まるため保持する",
            },
        },
        "required": ["tasks"],
    },
    "worker_instructions": (
        "タスク管理操作用ワーカー。タスクの追加、完了/未完了切替、名前変更、削除、完了済み一括削除、"
        "および各タスク詳細HTMLの編集を担当する。タスク詳細画面では AF.setChatContext により "
        "task_<id> の文脈になるため、『このタスク』『詳細に追記』は現在開いているタスクを優先して扱う。"
        "一覧画面には詳細本文を表示せず、詳細本文はタスクをクリックして開く詳細画面だけでレンダリングする。"
        "stateを直接更新する場合も selected_task_id は原則そのまま保持し、詳細編集後に一覧へ戻さない。"
        "詳細内容は plain text ではなく detail_html にHTML本文断片として保存する。ユーザーにHTMLを直接書かせず、"
        "依頼内容を h2/h3/p/ul/ol/li/strong/code/blockquote などの安全なHTMLに整えて反映する。"
        "『追加/入れて/作って』は add_task。『終わった/完了にして/未完了に戻して』は toggle_task。"
        "『名前を変えて/リネーム』は rename_task。『消して/削除』は delete_task、"
        "『完了済みを全部消して』は clear_done。『詳細を書いて/本文を作って/追記/HTMLで整えて』は "
        "state の該当 tasks[].detail_html を直接更新するか update_task_detail_html / append_task_detail_html を使う。"
        "『タスクを作って、詳細に〜を書いて』『タスクを追加して締切や注意点も入れて』のような複合命令は、"
        "タスク作成と detail_html/関連フィールド更新に分解して処理する。現在開いているタスクが一意なら対象として使う。"
        "タスク追加を含む依頼では、依頼全体から意味上のタスク名だけを抽出して title に入れ、説明・背景・目的・条件・"
        "メモ・案などは detail_html に分離する。断片的な詳細依頼はそのまま転記せず、内容に合う見出し・箇条書き・"
        "ラベルを付けて整理する。ユーザーに役立つ提案や不足観点を補える場合は、推測を確定事項にせず、"
        "『提案』『補足』『確認事項』として詳細へ加えてよい。"
        "対象タスクが不明なら聞き返す。詳細HTMLを置換するのか追記するのか曖昧な場合は、既存内容を活かして追記または整理する。"
    ),
    "worker_examples": [
        {"user": "買い物を追加して", "command": {"name": "add_task", "arguments": {"title": "買い物"}}, "reply": "タスクを追加します。"},
        {"user": "仙台出張準備を追加して、詳細に持ち物と確認事項を書いて", "command": {"name": "add_task", "arguments": {"title": "仙台出張準備", "detail_html": "<h2>持ち物と確認事項</h2><ul><li>持ち物を確認する</li><li>移動時間と予約を確認する</li></ul>"}}, "reply": "タスクを追加し、詳細も記入します。"},
        {"user": "買い物は終わった", "command": {"name": "toggle_task", "arguments": {"title": "買い物", "done": True}}, "reply": "完了にします。"},
        {"user": "買い物の詳細に、牛乳と卵を買うと書いて", "command": {"name": "update_task_detail_html", "arguments": {"title": "買い物", "detail_html": "<h2>買い物メモ</h2><ul><li>牛乳を買う</li><li>卵を買う</li></ul>"}}, "reply": "詳細をHTMLで更新します。"},
        {"user": "このタスクに注意点を追記して", "command": {"name": "append_task_detail_html", "arguments": {"detail_html": "<h3>注意点</h3><p>必要な確認事項を追記します。</p>"}}, "reply": "開いているタスクの詳細に追記します。"},
        {"user": "持っていくものとしてノートを詳細に追記して", "command": {"name": "append_task_detail_html", "arguments": {"detail_html": "<h3>持っていくもの</h3><ul><li>ノート</li></ul>"}}, "reply": "詳細に整理して追記します。"},
        {"user": "買い物を消して", "command": {"name": "delete_task", "arguments": {"title": "買い物"}}, "reply": "タスクを削除します。"},
        {"user": "完了済みを全部消して", "command": {"name": "clear_done", "arguments": {}}, "reply": "完了済みタスクを削除します。"},
    ],
}
