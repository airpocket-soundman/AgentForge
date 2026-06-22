"""Default mini-app template: タスク管理 (task_manager)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f4f6fb;--card:#fff;--ac:#4a7dff;--fg:#1f2545;--mut:#8a90ad;--done:#9aa0bd;--bd:#e7eaf3}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:620px;margin:0 auto;padding:16px;min-height:100%;display:flex;flex-direction:column}
h1{font-size:20px;margin:4px 2px 12px}
.add{display:flex;gap:8px}
.add input{flex:1;padding:12px;border:1px solid var(--bd);border-radius:10px;font-size:15px}
.add button{padding:0 18px;border:0;background:var(--ac);color:#fff;border-radius:10px;font-weight:700;cursor:pointer}
.filters{display:flex;gap:6px;margin:12px 2px 4px}
.filters button{border:1px solid var(--bd);background:#fff;border-radius:20px;padding:5px 12px;font-size:13px;color:var(--mut);cursor:pointer}
.filters button.on{background:var(--ac);color:#fff;border-color:var(--ac)}
ul{list-style:none;margin:8px 0;padding:0;flex:1}
li{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:11px 12px;margin-bottom:8px}
li.done .t{text-decoration:line-through;color:var(--done)}
.ck{width:22px;height:22px;border-radius:50%;border:2px solid var(--ac);flex:0 0 auto;cursor:pointer;display:grid;place-items:center;color:#fff;font-size:13px}
li.done .ck{background:var(--ac)}
.t{flex:1;font-size:15px;word-break:break-word}
.del{border:0;background:transparent;color:var(--mut);font-size:18px;cursor:pointer}
.empty{color:#aab;text-align:center;padding:30px}
.foot{color:var(--mut);font-size:13px;padding:6px 2px}
</style></head><body>
<div class="wrap">
  <h1>📋 タスク管理</h1>
  <div class="add"><input id="inp" placeholder="やることを入力してEnter…"><button id="addb">追加</button></div>
  <div class="filters"><button data-f="all" class="on">すべて</button><button data-f="active">未完了</button><button data-f="done">完了</button></div>
  <ul id="list"></ul>
  <div class="foot" id="foot"></div>
</div>
<script>
(function(){
  var tasks=[],filter='all',inp=document.getElementById('inp'),list=document.getElementById('list'),foot=document.getElementById('foot');
  function save(){AF.save({tasks:tasks});}
  function uid(){return 't'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);}
  function render(){
    var shown=tasks.filter(function(t){return filter==='all'||(filter==='done')===!!t.done;});
    list.innerHTML='';
    if(!shown.length){var d=document.createElement('div');d.className='empty';d.textContent='タスクはありません';list.appendChild(d);}
    shown.forEach(function(t){
      var li=document.createElement('li');if(t.done)li.className='done';
      var ck=document.createElement('div');ck.className='ck';ck.textContent=t.done?'✓':'';ck.onclick=function(){t.done=!t.done;save();render();};
      var sp=document.createElement('div');sp.className='t';sp.textContent=t.title;
      var del=document.createElement('button');del.className='del';del.textContent='×';del.onclick=function(){tasks=tasks.filter(function(x){return x.id!==t.id;});save();render();};
      li.appendChild(ck);li.appendChild(sp);li.appendChild(del);list.appendChild(li);
    });
    var left=tasks.filter(function(t){return !t.done;}).length;
    foot.textContent=tasks.length?(left+' 件 未完了 / 全 '+tasks.length+' 件'):'';
  }
  function add(title){title=(title||'').trim();if(!title)return;tasks.push({id:uid(),title:title,done:false});save();render();}
  document.getElementById('addb').onclick=function(){add(inp.value);inp.value='';inp.focus();};
  inp.addEventListener('keydown',function(e){if(e.key==='Enter'){add(inp.value);inp.value='';}});
  document.querySelectorAll('.filters button').forEach(function(b){b.onclick=function(){
    filter=b.getAttribute('data-f');document.querySelectorAll('.filters button').forEach(function(x){x.classList.remove('on');});b.classList.add('on');render();};});
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_task'){add(args.title);}
    else if(name==='toggle_task'){var t=tasks.find(function(x){return x.title===args.title;});if(t){t.done=args.done!==undefined?!!args.done:!t.done;save();render();}}
    else if(name==='rename_task'){var r=tasks.find(function(x){return x.title===args.title;});if(r&&args.new_title){r.title=args.new_title;save();render();}}
    else if(name==='delete_task'){tasks=tasks.filter(function(x){return x.title!==args.title;});save();render();}
    else if(name==='clear_done'){tasks=tasks.filter(function(x){return !x.done;});save();render();}
  };
  (async function(){var s=await AF.load();if(s&&Array.isArray(s.tasks))tasks=s.tasks;render();})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "task_manager",
    "title": "タスク管理",
    "description": "タスクの追加・完了・削除と未完了/完了の絞り込みができる ToDo。内容は自動保存されます。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "add_task", "description": "タスクを追加",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
        {"name": "toggle_task", "description": "完了/未完了を切替（done省略でトグル）",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "done": {"type": "boolean"}}, "required": ["title"]}},
        {"name": "rename_task", "description": "タスク名を変更",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "new_title": {"type": "string"}}, "required": ["title", "new_title"]}},
        {"name": "delete_task", "description": "タスクを削除",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
        {"name": "clear_done", "description": "完了タスクを一括削除", "inputSchema": {"type": "object", "properties": {}}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "タスク一覧",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "done": {"type": "boolean"},
                    },
                    "required": ["id", "title", "done"],
                },
            }
        },
        "required": ["tasks"],
    },
    "worker_instructions": (
        "タスク管理操作用ワーカー。タスクの追加、完了/未完了切替、名前変更、削除、完了済み一括削除を担当する。"
        "『追加/入れて/作って』は add_task。『終わった/完了にして/未完了に戻して』は toggle_task。"
        "『名前を変えて/リネーム』は rename_task。『消して/削除』は delete_task、"
        "『完了済みを全部消して』は clear_done。対象タスク名が不明なら聞き返す。"
    ),
    "worker_examples": [
        {"user": "買い物を追加して", "command": {"name": "add_task", "arguments": {"title": "買い物"}}, "reply": "タスクを追加します。"},
        {"user": "買い物は終わった", "command": {"name": "toggle_task", "arguments": {"title": "買い物", "done": True}}, "reply": "完了にします。"},
        {"user": "買い物を消して", "command": {"name": "delete_task", "arguments": {"title": "買い物"}}, "reply": "タスクを削除します。"},
        {"user": "完了済みを全部消して", "command": {"name": "clear_done", "arguments": {}}, "reply": "完了済みタスクを削除します。"},
    ],
}
