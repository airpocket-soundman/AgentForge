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
  function snapshot(){return {c:c,op:op,prev:prev,sub:sub,done:done,hist:hist};}
  function save(){try{AF.save(snapshot());}catch(_){}}
  function restore(s){
    if(!s||typeof s!=='object')return;
    c=String(s.c||'0');
    op=(typeof s.op==='string'&&'+−×÷'.indexOf(s.op)>=0)?s.op:null;
    prev=(s.prev===null||s.prev===undefined)?null:String(s.prev);
    sub=String(s.sub||'');
    done=!!s.done;
    hist=Array.isArray(s.hist)?s.hist.slice(0,20).map(function(h){return {e:String(h.e||''),v:String(h.v||'0')};}):[];
  }
  function draw(){mainEl.textContent=c;subEl.textContent=sub;
    var L=c.length;mainEl.style.fontSize=(L>16?'18px':L>12?'24px':L>9?'30px':'40px');}
  function emptyHist(){
    histEl.replaceChildren();
    var e=document.createElement('div');e.className='h-empty';e.textContent='履歴はまだありません';histEl.appendChild(e);
  }
  function drawHist(){
    if(!hist.length){emptyHist();return;}
    histEl.replaceChildren();hist.forEach(function(h){var r=document.createElement('div');r.className='h-row';
      var e=document.createElement('span');e.textContent=h.e;var v=document.createElement('b');v.textContent=h.v;
      r.appendChild(e);r.appendChild(v);r.onclick=function(){c=h.v;sub=h.e+' =';done=true;draw();save();};histEl.appendChild(r);});
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
    draw();save();
  }
  function tokenize(input){
    var s=String(input||'').replace(/\s+/g,'').replace(/－/g,'−').replace(/×/g,'*').replace(/÷/g,'/');
    var out=[],i=0;
    while(i<s.length){
      if(s.slice(i,i+2).toUpperCase()==='AC'){out.push('AC');i+=2;continue;}
      if(s.slice(i,i+3)==='+/-'||s.slice(i,i+2)==='±'){out.push('+/-');i+=s.slice(i,i+3)==='+/-'?3:2;continue;}
      var ch=s[i],map={'*':'×','/':'÷','-':'−'};
      out.push(map[ch]||ch);i+=1;
    }
    return out;
  }
  function resetNoSave(){c='0';op=null;prev=null;sub='';done=false;}
  document.querySelectorAll('button[data-k]').forEach(function(b){b.addEventListener('pointerdown',function(e){e.preventDefault();key(b.getAttribute('data-k'));});});
  // Specialist Worker content tools
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='press'){tokenize(args.keys||'').forEach(key);}
    else if(name==='clear'){key('AC');}
    else if(name==='compute'){resetNoSave();tokenize(args.expression||'').forEach(key);key('=');}
  };
  (async function(){try{restore(await AF.load());}catch(_){}drawHist();draw();})();
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
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "c": {"type": "string", "description": "現在表示中の値"},
            "op": {"type": ["string", "null"], "enum": ["+", "−", "×", "÷", None], "description": "保留中の演算子"},
            "prev": {"type": ["string", "null"], "description": "保留中の左辺値"},
            "sub": {"type": "string", "description": "上段表示"},
            "done": {"type": "boolean", "description": "直前操作が演算確定/演算子入力か"},
            "hist": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {"e": {"type": "string"}, "v": {"type": "string"}},
                    "required": ["e", "v"],
                },
            },
        },
        "required": ["c", "op", "prev", "sub", "done", "hist"],
    },
    "worker_instructions": (
        "電卓操作用ワーカー。計算式の実行、キー入力、全消去を担当する。"
        "数式が含まれる依頼は compute。『押して/入力して』は press。『クリア/消して/リセット』は clear。"
        "式が曖昧なら、計算したい式を聞き返す。"
    ),
    "worker_examples": [
        {"user": "12+3を計算して", "command": {"name": "compute", "arguments": {"expression": "12+3"}}, "reply": "計算します。"},
        {"user": "ACして", "command": {"name": "clear", "arguments": {}}, "reply": "電卓をクリアします。"},
        {"user": "1 2 + 3 を押して", "command": {"name": "press", "arguments": {"keys": "12+3"}}, "reply": "キーを入力します。"},
    ],
    "worker_eval_cases": [
        {"input": "12+3を計算して", "expected_behavior": "execute_command", "expected_state_diff": "c が 15、hist 先頭に 12 + 3 の結果が追加される", "expected_message_contains": "計算"},
        {"input": "ACして", "expected_behavior": "execute_command", "expected_state_diff": "c が 0、op/prev が null になる", "expected_message_contains": "クリア"},
        {"input": "ACを押してから7×8", "expected_behavior": "execute_command", "expected_state_diff": "AC を1トークンとして扱い、A/Cに分解しない", "expected_message_contains": ""},
        {"input": "何を計算する？", "expected_behavior": "reply_or_clarify", "expected_state_diff": "", "expected_message_contains": "式"},
    ],
    "clarification_policy": "計算式や押すキー列が不明な場合は、実行前に計算したい式を短く聞き返す。",
    "dangerous_action_policy": "AC/全消去は現在表示と保留演算を消すが、履歴は残る。履歴を消す操作が追加される場合は実行前に確認する。",
}
