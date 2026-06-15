"""Default mini-app template: 電卓 (calculator)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef0fb;--card:#fff;--key:#fff;--keyb:#e6e8f5;--op:#5b6cf0;--fg:#1f2240;--mut:#7a7f9a}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg);display:grid;place-items:center;padding:12px}
.calc{width:100%;max-width:340px;background:var(--card);border-radius:18px;box-shadow:0 10px 30px #0001;padding:16px}
.disp{text-align:right;padding:10px 8px 6px}
.sub{min-height:18px;color:var(--mut);font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.main{font-size:40px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:clip}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px}
button{border:0;border-radius:12px;padding:16px 0;font-size:18px;font-weight:600;background:var(--key);
 box-shadow:0 1px 0 var(--keyb);cursor:pointer;color:var(--fg)}
button:active{transform:translateY(1px)}
.k-fn{background:var(--keyb)}.k-op{background:var(--op);color:#fff}.k-eq{background:var(--op);color:#fff}
.hist{margin-top:12px;height:140px;overflow-y:auto;border-top:1px solid #eee;padding-top:6px}
.h-row{display:flex;justify-content:space-between;font-size:13px;color:var(--mut);padding:3px 2px;cursor:pointer}
.h-row:hover{background:#f5f6ff;border-radius:6px}.h-empty{color:#aab;font-size:13px;padding:4px}
</style></head><body>
<div class="calc">
  <div class="disp"><div class="sub" id="sub"></div><div class="main" id="main">0</div></div>
  <div class="grid">
    <button class="k-fn" data-k="AC">AC</button><button class="k-fn" data-k="+/-">+/−</button>
    <button class="k-fn" data-k="%">%</button><button class="k-op" data-k="÷">÷</button>
    <button data-k="7">7</button><button data-k="8">8</button><button data-k="9">9</button><button class="k-op" data-k="×">×</button>
    <button data-k="4">4</button><button data-k="5">5</button><button data-k="6">6</button><button class="k-op" data-k="−">−</button>
    <button data-k="1">1</button><button data-k="2">2</button><button data-k="3">3</button><button class="k-op" data-k="+">+</button>
    <button data-k="0" style="grid-column:span 2">0</button><button data-k=".">.</button><button class="k-eq" data-k="=">=</button>
  </div>
  <div class="hist" id="hist"><div class="h-empty">履歴はまだありません</div></div>
</div>
<script>
(function(){
  var c='0',op=null,prev=null,sub='',done=false,hist=[];
  var mainEl=document.getElementById('main'),subEl=document.getElementById('sub'),histEl=document.getElementById('hist');
  function fmt(n){if(n!==n)return 'Error';if(!isFinite(n))return n>0?'∞':'-∞';return parseFloat(n.toPrecision(12)).toString();}
  function draw(){mainEl.textContent=c;subEl.textContent=sub;
    var L=c.length;mainEl.style.fontSize=(L>16?'18px':L>12?'24px':L>9?'30px':'40px');}
  function drawHist(){
    if(!hist.length){histEl.innerHTML='<div class="h-empty">履歴はまだありません</div>';return;}
    histEl.innerHTML='';hist.forEach(function(h){var r=document.createElement('div');r.className='h-row';
      r.innerHTML='<span>'+h.e+'</span><b>'+h.v+'</b>';r.onclick=function(){c=h.v;sub=h.e+' =';done=true;draw();};histEl.appendChild(r);});
  }
  function calc(a,o,b){a=+a;b=+b;return o==='+'?a+b:o==='−'?a-b:o==='×'?a*b:o==='÷'?(b===0?NaN:a/b):NaN;}
  function key(k){
    if(k==='AC'){c='0';op=null;prev=null;sub='';done=false;}
    else if(k==='+/-'){if(c!=='Error')c=c[0]==='-'?c.slice(1):'-'+c;}
    else if(k==='%'){if(c!=='Error')c=fmt(parseFloat(c)/100);}
    else if('+−×÷'.indexOf(k)>=0){if(op&&!done&&prev!==null){var r=calc(prev,op,c);prev=fmt(r);c=fmt(r);}else prev=c;op=k;sub=prev+' '+k;done=true;}
    else if(k==='='){if(op&&prev!==null){var e=sub+' '+c,r2=calc(prev,op,c),rs=fmt(r2);hist.unshift({e:e,v:rs});if(hist.length>20)hist.pop();drawHist();c=rs;sub=e+' =';op=null;prev=null;done=true;}}
    else if(k==='.'){if(done){c='0.';done=false;}else if(c.indexOf('.')<0)c+='.';}
    else{if(done||c==='0'){c=(c==='-0'?'-':'')+k;done=false;}else if(c==='Error')c=k;else c+=k;}
    draw();
  }
  document.querySelectorAll('button[data-k]').forEach(function(b){b.addEventListener('pointerdown',function(e){e.preventDefault();key(b.getAttribute('data-k'));});});
  // Specialist Worker content tools
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='press'){String(args.keys||'').split('').forEach(function(ch){
      var map={'*':'×','/':'÷','-':'−'};key(map[ch]||ch);});}
    else if(name==='clear'){key('AC');}
    else if(name==='compute'){ (String(args.expression||'')).split('').forEach(function(ch){var map={'*':'×','/':'÷','-':'−'};key(map[ch]||ch);});key('=');}
  };
})();
</script></body></html>"""

MANIFEST = {
    "feature": "calculator",
    "title": "電卓",
    "description": "四則演算・%・符号反転・計算履歴つきの電卓。履歴をタップで再利用できます。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "press", "description": "キー列を順に押す（例 12+3）",
         "inputSchema": {"type": "object", "properties": {"keys": {"type": "string"}}, "required": ["keys"]}},
        {"name": "compute", "description": "式を入力して=まで実行",
         "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
        {"name": "clear", "description": "全消去(AC)", "inputSchema": {"type": "object", "properties": {}}},
    ],
}
