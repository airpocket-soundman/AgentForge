"""Default mini-app template: 翻訳 (translate).

The sandbox has no network, so the translation itself is done by the Specialist
Worker (an LLM) via the app chat: the user types text, asks "英語にして" in the
chat, and the worker fills the result through the set_translation command. The
UI is the input/output surface + a small local phrasebook for offline reuse.
"""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef4fb;--card:#fff;--ac:#2f74c0;--fg:#1b2c3e;--mut:#7f93a8;--bd:#dde7f1}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:720px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 2px 6px}
.hint{font-size:12.5px;color:var(--mut);margin:0 2px 12px}
.langs{display:flex;align-items:center;gap:8px;margin-bottom:8px}
select{padding:8px;border:1px solid var(--bd);border-radius:8px;background:#fff;font-size:14px}
.swap{border:1px solid var(--bd);background:#fff;border-radius:8px;padding:8px 10px;cursor:pointer}
.box{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:10px;margin-bottom:10px}
.box label{font-size:12px;color:var(--mut)}
textarea{width:100%;border:0;resize:vertical;min-height:90px;font-size:16px;font-family:inherit;background:transparent;color:var(--fg)}
textarea:focus{outline:none}
.out{min-height:90px;font-size:16px;white-space:pre-wrap;word-break:break-word}
.row{display:flex;gap:8px}
.row button{flex:1;border:0;border-radius:10px;padding:11px;font-weight:700;cursor:pointer}
.b-save{background:#fff;border:1px solid var(--bd);color:var(--ac)}
.tip{background:#e7f0fb;border-radius:10px;padding:10px;font-size:13px;color:#3a5a78;margin-bottom:10px}
.pb{list-style:none;margin:8px 0 0;padding:0}
.pb li{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--bd);padding:8px 4px;font-size:14px}
.pb .src{color:var(--mut)}.pb .x{cursor:pointer;color:var(--mut);border:0;background:none}
h2{font-size:14px;margin:16px 2px 4px;color:var(--ac)}
</style></head><body>
<div class="wrap">
  <h1>🌐 翻訳</h1>
  <p class="hint">下のチャットで「英語にして」「日本語に訳して」と頼むと、専門ワーカーが訳して下の枠に表示します。</p>
  <div class="tip" id="tip">原文を入力し、下のアプリチャットに「英語にして」等と送ってください。よく使う訳は「保存」で単語帳に残せます。</div>
  <div class="langs">
    <select id="from"><option value="auto">自動判定</option><option value="ja">日本語</option><option value="en">英語</option><option value="zh">中国語</option><option value="ko">韓国語</option><option value="fr">フランス語</option></select>
    <button class="swap" id="swap">⇅</button>
    <select id="to"><option value="en">英語</option><option value="ja">日本語</option><option value="zh">中国語</option><option value="ko">韓国語</option><option value="fr">フランス語</option></select>
  </div>
  <div class="box"><label>原文</label><textarea id="src" placeholder="翻訳したい文章…"></textarea></div>
  <div class="box"><label>訳文</label><div class="out" id="out"></div></div>
  <div class="row"><button class="b-save" id="saveb">⭐ 単語帳に保存</button></div>
  <h2>単語帳（オフライン）</h2>
  <ul class="pb" id="pb"></ul>
</div>
<script>
(function(){
  var book=[],srcEl=document.getElementById('src'),outEl=document.getElementById('out'),pbEl=document.getElementById('pb');
  var fromEl=document.getElementById('from'),toEl=document.getElementById('to');
  function save(){AF.save({book:book,from:fromEl.value,to:toEl.value});}
  function renderBook(){pbEl.innerHTML='';book.forEach(function(p,i){
    var li=document.createElement('li');
    li.innerHTML='<span class="src"></span><span class="dst"></span><button class="x">×</button>';
    li.querySelector('.src').textContent=p.src;li.querySelector('.dst').textContent=p.dst;
    li.querySelector('.x').onclick=function(){book.splice(i,1);save();renderBook();};
    li.onclick=function(e){if(e.target.className==='x')return;srcEl.value=p.src;outEl.textContent=p.dst;};
    pbEl.appendChild(li);});}
  document.getElementById('swap').onclick=function(){var a=fromEl.value;if(a==='auto')return;fromEl.value=toEl.value;toEl.value=a;save();};
  document.getElementById('saveb').onclick=function(){var s=srcEl.value.trim(),d=(outEl.textContent||'').trim();if(s&&d){book.unshift({src:s,dst:d});if(book.length>200)book.pop();save();renderBook();}};
  srcEl.addEventListener('input',save);fromEl.onchange=save;toEl.onchange=save;
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='set_translation'){outEl.textContent=args.text||'';document.getElementById('tip').style.display='none';}
    else if(name==='set_source'){srcEl.value=args.text||'';}
    else if(name==='set_languages'){if(args.from)fromEl.value=args.from;if(args.to)toEl.value=args.to;save();}
    else if(name==='save_phrase'){if(args.src&&args.dst){book.unshift({src:args.src,dst:args.dst});save();renderBook();}}
  };
  (async function(){var s=await AF.load();if(s){if(Array.isArray(s.book))book=s.book;if(s.from)fromEl.value=s.from;if(s.to)toEl.value=s.to;}renderBook();})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "translate",
    "title": "翻訳",
    "description": "原文を入力し、アプリチャットで「英語にして」等と頼むと専門ワーカーが訳して表示。よく使う訳は単語帳に保存できます。",
    "kind": "app",
    "theme": "ocean",
    "html": _HTML,
    "commands": [
        {"name": "set_translation", "description": "訳文を訳文欄に表示する（翻訳結果）",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "set_source", "description": "原文欄に文章を入れる",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "set_languages", "description": "翻訳元/先の言語を設定",
         "inputSchema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}}}},
        {"name": "save_phrase", "description": "原文と訳を単語帳に保存",
         "inputSchema": {"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}},
    ],
}
