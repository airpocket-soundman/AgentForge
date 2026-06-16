"""Default mini-app template: 翻訳 (translate).

No worker chat: the app has its own 「翻訳」 button that invokes the Specialist
Worker via AF.askWorker (the sandbox has no network, so the LLM worker does the
translation). The source can be text AND/OR a pasted image — text inside the
image is translated too (vision). Frequently used results go to an offline
phrasebook.
"""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef4fb;--card:#fff;--ac:#2f74c0;--fg:#1b2c3e;--mut:#7f93a8;--bd:#dde7f1}
*{box-sizing:border-box}html,body{margin:0;min-height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 2px 4px}
.hint{font-size:12.5px;color:var(--mut);margin:0 2px 12px}
.langs{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
select{padding:8px;border:1px solid var(--bd);border-radius:8px;background:#fff;font-size:14px}
.swap{border:1px solid var(--bd);background:#fff;border-radius:8px;padding:8px 10px;cursor:pointer}
.box{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:10px;margin-bottom:10px}
.box label{font-size:12px;color:var(--mut)}
textarea{width:100%;border:0;resize:vertical;min-height:84px;font-size:16px;font-family:inherit;background:transparent;color:var(--fg)}
textarea:focus{outline:none}
.out{min-height:84px;font-size:16px;white-space:pre-wrap;word-break:break-word}
.drop{margin-top:8px;border:1.5px dashed var(--bd);border-radius:10px;padding:10px;text-align:center;color:var(--mut);font-size:13px;cursor:pointer}
.drop.over{border-color:var(--ac);background:#f3f8fe}
.thumb{margin-top:8px;display:none}
.thumb img{max-width:100%;max-height:200px;border-radius:8px;border:1px solid var(--bd)}
.thumb .rm{margin-top:4px;border:0;background:none;color:var(--mut);cursor:pointer;font-size:12px}
.go{width:100%;border:0;border-radius:12px;padding:14px;font-size:16px;font-weight:700;background:var(--ac);color:#fff;cursor:pointer}
.go:disabled{opacity:.55;cursor:default}
.status{font-size:13px;color:var(--ac);min-height:18px;margin:6px 2px}
.b-save{margin-top:8px;border:1px solid var(--bd);background:#fff;color:var(--ac);border-radius:10px;padding:9px 14px;cursor:pointer}
.pb{list-style:none;margin:8px 0 0;padding:0}
.pb li{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--bd);padding:8px 4px;font-size:14px;cursor:pointer}
.pb .src{color:var(--mut)}.pb .x{cursor:pointer;color:var(--mut);border:0;background:none}
h2{font-size:14px;margin:16px 2px 4px;color:var(--ac)}
</style></head><body>
<div class="wrap">
  <h1>🌐 翻訳</h1>
  <p class="hint">原文を入力（または画像を貼り付け）→「翻訳」を押すと、専門ワーカーが訳します。画像内の文字も翻訳します。</p>
  <div class="langs">
    <select id="from"><option value="auto">自動判定</option><option value="ja">日本語</option><option value="en">英語</option><option value="zh">中国語</option><option value="ko">韓国語</option><option value="fr">フランス語</option></select>
    <button class="swap" id="swap" title="入れ替え">⇅</button>
    <select id="to"><option value="ja">日本語</option><option value="en">英語</option><option value="zh">中国語</option><option value="ko">韓国語</option><option value="fr">フランス語</option></select>
  </div>
  <div class="box">
    <label>原文（テキスト / 画像）</label>
    <textarea id="src" placeholder="翻訳したい文章…（画像はここに貼り付け・下にドロップも可）"></textarea>
    <div class="drop" id="drop">🖼 画像をドロップ / クリックして選択（画像内の英語なども翻訳）</div>
    <input type="file" id="file" accept="image/*" style="display:none">
    <div class="thumb" id="thumb"><img id="thumbimg" alt="貼り付け画像"><div><button class="rm" id="rm">× 画像を外す</button></div></div>
  </div>
  <button class="go" id="go">翻訳する</button>
  <div class="status" id="status"></div>
  <div class="box"><label>訳文</label><div class="out" id="out"></div></div>
  <button class="b-save" id="saveb">⭐ 単語帳に保存</button>
  <h2>単語帳（オフライン）</h2>
  <ul class="pb" id="pb"></ul>
</div>
<script>
(function(){
  var LBL={auto:'自動判定',ja:'日本語',en:'英語',zh:'中国語',ko:'韓国語',fr:'フランス語'};
  var book=[],img=null;
  var srcEl=document.getElementById('src'),outEl=document.getElementById('out'),pbEl=document.getElementById('pb');
  var fromEl=document.getElementById('from'),toEl=document.getElementById('to'),statusEl=document.getElementById('status');
  var goEl=document.getElementById('go'),thumb=document.getElementById('thumb'),thumbimg=document.getElementById('thumbimg');
  function save(){AF.save({book:book,from:fromEl.value,to:toEl.value});}
  function renderBook(){pbEl.innerHTML='';book.forEach(function(p,i){
    var li=document.createElement('li');
    li.innerHTML='<span class="src"></span><span class="dst"></span><button class="x">×</button>';
    li.querySelector('.src').textContent=p.src;li.querySelector('.dst').textContent=p.dst;
    li.querySelector('.x').onclick=function(e){e.stopPropagation();book.splice(i,1);save();renderBook();};
    li.onclick=function(){srcEl.value=p.src;outEl.textContent=p.dst;};
    pbEl.appendChild(li);});}
  function setImg(dataUrl){img=dataUrl||null;if(img){thumbimg.src=img;thumb.style.display='block';}else{thumb.style.display='none';}}
  function readFile(f){if(!f||!/^image\//.test(f.type))return;var r=new FileReader();r.onload=function(){setImg(r.result);};r.readAsDataURL(f);}
  // paste / drop / pick image
  srcEl.addEventListener('paste',function(e){var it=(e.clipboardData||{}).items||[];for(var i=0;i<it.length;i++){if(it[i].type&&it[i].type.indexOf('image')===0){readFile(it[i].getAsFile());e.preventDefault();return;}}});
  var drop=document.getElementById('drop'),file=document.getElementById('file');
  drop.onclick=function(){file.click();};
  file.onchange=function(){readFile(file.files[0]);};
  drop.addEventListener('dragover',function(e){e.preventDefault();drop.classList.add('over');});
  drop.addEventListener('dragleave',function(){drop.classList.remove('over');});
  drop.addEventListener('drop',function(e){e.preventDefault();drop.classList.remove('over');readFile((e.dataTransfer.files||[])[0]);});
  document.getElementById('rm').onclick=function(){setImg(null);file.value='';};
  document.getElementById('swap').onclick=function(){var a=fromEl.value;if(a==='auto')return;fromEl.value=toEl.value;toEl.value=a;save();};
  // translate via the Specialist Worker
  goEl.onclick=async function(){
    var text=srcEl.value.trim();
    if(!text&&!img){statusEl.textContent='原文を入力するか、画像を貼り付けてください。';return;}
    goEl.disabled=true;statusEl.textContent='翻訳中…';outEl.textContent='';
    var fromL=LBL[fromEl.value]||'自動判定',toL=LBL[toEl.value]||'日本語';
    var instr='次の原文を'+toL+'に翻訳し、set_translation ツールで訳文だけを返してください。'
      +(fromEl.value!=='auto'?'（原文の言語: '+fromL+'）':'')
      +(img?'添付画像内のテキストも読み取って翻訳対象に含めてください。':'')
      +(text?('\n原文:\n'+text):'');
    try{
      var res=await AF.askWorker(instr,{images:img?[img]:[]});
      if(!outEl.textContent && res && res.reply){statusEl.textContent='';/* set_translation で表示済みのはず */}
      statusEl.textContent='';
    }catch(_){statusEl.textContent='翻訳に失敗しました。少し待って再度お試しください。';}
    goEl.disabled=false;
  };
  document.getElementById('saveb').onclick=function(){var s=srcEl.value.trim(),d=(outEl.textContent||'').trim();if(s&&d){book.unshift({src:s,dst:d});if(book.length>200)book.pop();save();renderBook();}};
  srcEl.addEventListener('input',save);fromEl.onchange=save;toEl.onchange=save;
  // Specialist Worker → app content tools
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='set_translation'){outEl.textContent=args.text||'';statusEl.textContent='';}
    else if(name==='set_source'){srcEl.value=args.text||'';}
    else if(name==='set_languages'){if(args.from)fromEl.value=args.from;if(args.to)toEl.value=args.to;save();}
    else if(name==='save_phrase'){if(args.src&&args.dst){book.unshift({src:args.src,dst:args.dst});save();renderBook();}}
  };
  // This default has its own translate button → hide the app-chat panel.
  try{AF.setChatVisible(false);}catch(_){}
  (async function(){var s=await AF.load();if(s){if(Array.isArray(s.book))book=s.book;if(s.from)fromEl.value=s.from;if(s.to)toEl.value=s.to;}renderBook();})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "translate",
    "title": "翻訳",
    "description": "原文（テキスト/画像）を入力し「翻訳」ボタンで専門ワーカーが翻訳。画像内の文字も訳せます。よく使う訳は単語帳に保存。",
    "kind": "app",
    "theme": "ocean",
    "html": _HTML,
    "commands": [
        {"name": "set_translation", "description": "訳文を訳文欄に表示する（翻訳結果の本文）",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "set_source", "description": "原文欄に文章を入れる",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        {"name": "set_languages", "description": "翻訳元/先の言語を設定（ja/en/zh/ko/fr/auto）",
         "inputSchema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}}}},
        {"name": "save_phrase", "description": "原文と訳を単語帳に保存",
         "inputSchema": {"type": "object", "properties": {"src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}},
    ],
}
