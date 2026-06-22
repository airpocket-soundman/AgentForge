"""Default mini-app template: メモ帳 (memo)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#fffaf2;--card:#fff;--ac:#e08a2b;--fg:#3a2f22;--mut:#a99a85;--bd:#efe6d6}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.app{display:flex;height:100%;max-width:900px;margin:0 auto}
.side{flex:0 0 240px;border-right:1px solid var(--bd);display:flex;flex-direction:column;background:#fffdf8}
.side h1{font-size:16px;margin:0;padding:14px}
.newb{margin:0 12px 8px;padding:10px;border:0;background:var(--ac);color:#fff;border-radius:10px;font-weight:700;cursor:pointer}
.notes{list-style:none;margin:0;padding:0 8px 8px;overflow:auto;flex:1}
.notes li{padding:10px;border-radius:8px;cursor:pointer;margin-bottom:4px}
.notes li.on{background:#fdeccd}
.notes .nt{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.notes .nm{font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.main{flex:1;display:flex;flex-direction:column;padding:14px}
.main input{font-size:18px;font-weight:700;border:0;border-bottom:1px solid var(--bd);padding:8px 4px;background:transparent;color:var(--fg)}
.main textarea{flex:1;border:0;resize:none;font-size:15px;line-height:1.7;padding:12px 4px;background:transparent;color:var(--fg);font-family:inherit}
.main input:focus,.main textarea:focus{outline:none}
.bar{display:flex;justify-content:flex-end;gap:8px}
.bar button{border:1px solid var(--bd);background:#fff;color:var(--mut);border-radius:8px;padding:6px 12px;cursor:pointer}
.empty{margin:auto;color:#bbae98}
@media(max-width:620px){.app{flex-direction:column}.side{flex:0 0 auto;max-height:38%;border-right:0;border-bottom:1px solid var(--bd)}.notes{display:flex;gap:6px;flex-wrap:wrap}.notes li{flex:1 1 40%}}
</style></head><body>
<div class="app">
  <div class="side">
    <h1>📝 メモ帳</h1><button class="newb" id="newb">＋ 新規メモ</button>
    <ul class="notes" id="notes"></ul>
  </div>
  <div class="main" id="main"><div class="empty">メモを選ぶか「＋ 新規メモ」で作成</div></div>
</div>
<script>
(function(){
  var notes=[],cur=null,notesEl=document.getElementById('notes'),mainEl=document.getElementById('main');
  function save(){AF.save({notes:notes});}
  function uid(){return 'n'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);}
  function title(n){return (n.title||'').trim()||(n.body||'').split('\n')[0].slice(0,20)||'無題';}
  function renderList(){
    notesEl.innerHTML='';
    notes.slice().sort(function(a,b){return (b.updated||0)-(a.updated||0);}).forEach(function(n){
      var li=document.createElement('li');if(cur&&n.id===cur.id)li.className='on';
      li.innerHTML='<div class="nt"></div><div class="nm"></div>';
      li.querySelector('.nt').textContent=title(n);
      li.querySelector('.nm').textContent=(n.body||'').replace(/\n/g,' ').slice(0,30)||'（本文なし）';
      li.onclick=function(){open(n);};notesEl.appendChild(li);
    });
  }
  function open(n){cur=n;
    mainEl.innerHTML='';
    var ti=document.createElement('input');ti.placeholder='タイトル';ti.value=n.title||'';
    var ta=document.createElement('textarea');ta.placeholder='本文…';ta.value=n.body||'';
    var bar=document.createElement('div');bar.className='bar';
    var del=document.createElement('button');del.textContent='🗑 削除';
    function touch(){n.title=ti.value;n.body=ta.value;n.updated=Date.now();save();renderList();}
    ti.oninput=touch;ta.oninput=touch;
    del.onclick=function(){notes=notes.filter(function(x){return x.id!==n.id;});cur=null;save();renderList();mainEl.innerHTML='<div class="empty">メモを選ぶか「＋ 新規メモ」で作成</div>';};
    bar.appendChild(del);mainEl.appendChild(ti);mainEl.appendChild(ta);mainEl.appendChild(bar);ta.focus();renderList();
  }
  function add(t,b){var n={id:uid(),title:t||'',body:b||'',updated:Date.now()};notes.push(n);save();open(n);}
  document.getElementById('newb').onclick=function(){add('','');};
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_note'){add(args.title,args.body);}
    else if(name==='update_note'){var u=notes.find(function(x){return title(x)===args.title;});if(u){if(args.new_title!==undefined)u.title=args.new_title;if(args.body!==undefined)u.body=args.body;u.updated=Date.now();save();open(u);}}
    else if(name==='append_note'){var n=cur||notes[0];if(n){n.body=(n.body?n.body+'\n':'')+(args.text||'');n.updated=Date.now();save();open(n);}}
    else if(name==='delete_note'){notes=notes.filter(function(x){return title(x)!==args.title;});if(cur&&notes.indexOf(cur)<0)cur=null;save();renderList();}
  };
  (async function(){var s=await AF.load();if(s&&Array.isArray(s.notes))notes=s.notes;renderList();if(notes.length)open(notes[0]);})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "memo",
    "title": "メモ帳",
    "description": "複数のメモを作成・編集・削除できるノート。タイトル＋本文を自動保存します。",
    "kind": "app",
    "theme": "warm",
    "html": _HTML,
    "commands": [
        {"name": "add_note", "description": "新しいメモを作成",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}}},
        {"name": "update_note", "description": "タイトル一致のメモを更新（new_title/body）",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "new_title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title"]}},
        {"name": "append_note", "description": "現在のメモに本文を追記",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "delete_note", "description": "タイトル一致のメモを削除",
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "notes": {
                "type": "array",
                "description": "メモ一覧",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "updated": {"type": "number"},
                    },
                    "required": ["id", "title", "body"],
                },
            }
        },
        "required": ["notes"],
    },
    "worker_instructions": (
        "メモ帳操作用ワーカー。メモの作成、本文更新、本文追記、削除を担当する。"
        "『新しいメモ/メモを作って』は add_note。『本文を変えて/書き換えて』は update_note。"
        "『追記/書き足して』は append_note。『消して/削除』は delete_note。"
        "削除や更新で対象タイトルが不明なら、どのメモか聞き返す。"
    ),
    "worker_examples": [
        {"user": "買い物メモを作って", "command": {"name": "add_note", "arguments": {"title": "買い物", "body": ""}}, "reply": "メモを作成します。"},
        {"user": "牛乳も追記して", "command": {"name": "append_note", "arguments": {"text": "牛乳"}}, "reply": "現在のメモに追記します。"},
        {"user": "買い物メモを消して", "command": {"name": "delete_note", "arguments": {"title": "買い物"}}, "reply": "メモを削除します。"},
        {"user": "本文を書き換えて", "command": {"name": "", "arguments": {}}, "reply": "どのメモを、どんな本文に変更しますか？"},
    ],
}
