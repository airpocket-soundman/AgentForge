"""Default mini-app template: ペイント (paint)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f3f3f7;--bar:#fff;--ac:#6c5ce7;--bd:#e3e3ee;--fg:#2a2a40}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg);display:flex;flex-direction:column}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 10px;background:var(--bar);border-bottom:1px solid var(--bd)}
.swatch{width:26px;height:26px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px var(--bd);cursor:pointer}
.swatch.on{box-shadow:0 0 0 2px var(--ac)}
.tool{border:1px solid var(--bd);background:#fff;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:14px}
.tool.on{background:var(--ac);color:#fff;border-color:var(--ac)}
input[type=range]{width:100px}
.sep{flex:1}
canvas{flex:1;touch-action:none;background:#fff;display:block}
.wrap{flex:1;position:relative}
</style></head><body>
<div class="bar">
  <span id="sw"></span>
  <input type="color" id="cp" value="#222222" title="色を選ぶ">
  <span class="tool" style="cursor:default">太さ</span><input type="range" id="size" min="1" max="40" value="4">
  <button class="tool on" id="pen" data-tool="pen">✏️ ペン</button>
  <button class="tool" id="eraser" data-tool="eraser">🩹 消しゴム</button>
  <span class="sep"></span>
  <button class="tool" id="undo">↶ 戻す</button>
  <button class="tool" id="clear">🗑 全消去</button>
  <button class="tool" id="save">💾 保存</button>
</div>
<div class="wrap"><canvas id="cv"></canvas></div>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  var color='#222222',size=4,tool='pen',drawing=false,last=null,undoStack=[];
  var PALETTE=['#222222','#e74c3c','#e67e22','#f1c40f','#2ecc71','#3498db','#9b59b6','#ffffff'];
  function fit(){var r=cv.parentNode.getBoundingClientRect();var img=ctx.getImageData(0,0,cv.width||1,cv.height||1);
    cv.width=r.width;cv.height=r.height;ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);try{ctx.putImageData(img,0,0);}catch(_){}}
  function pushUndo(){try{undoStack.push(cv.toDataURL());if(undoStack.length>20)undoStack.shift();}catch(_){}}
  function pos(e){var r=cv.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};}
  function start(e){e.preventDefault();pushUndo();drawing=true;last=pos(e);dot(last);}
  function move(e){if(!drawing)return;var p=pos(e);line(last,p);last=p;}
  function end(){drawing=false;last=null;persist();}
  function stroke(){ctx.lineCap='round';ctx.lineJoin='round';ctx.lineWidth=size;
    ctx.strokeStyle=tool==='eraser'?'#ffffff':color;ctx.fillStyle=ctx.strokeStyle;}
  function dot(p){stroke();ctx.beginPath();ctx.arc(p.x,p.y,size/2,0,7);ctx.fill();}
  function line(a,b){stroke();ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  var saveT;function persist(){clearTimeout(saveT);saveT=setTimeout(function(){try{AF.saveBlob('canvas',cv.toDataURL('image/png'));}catch(_){}}, 600);}
  function clearAll(){pushUndo();ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);persist();}
  function undo(){var d=undoStack.pop();if(!d)return;var im=new Image();im.onload=function(){ctx.clearRect(0,0,cv.width,cv.height);ctx.drawImage(im,0,0);persist();};im.src=d;}
  // palette
  var swEl=document.getElementById('sw');PALETTE.forEach(function(c){var s=document.createElement('span');s.className='swatch'+(c===color?' on':'');s.style.background=c;
    s.onclick=function(){color=c;tool='pen';document.getElementById('cp').value=c;setTool();document.querySelectorAll('.swatch').forEach(function(x){x.classList.remove('on');});s.classList.add('on');};swEl.appendChild(s);});
  document.getElementById('cp').oninput=function(e){color=e.target.value;tool='pen';setTool();};
  document.getElementById('size').oninput=function(e){size=+e.target.value;};
  function setTool(){document.querySelectorAll('[data-tool]').forEach(function(b){b.classList.toggle('on',b.getAttribute('data-tool')===tool);});}
  document.getElementById('pen').onclick=function(){tool='pen';setTool();};
  document.getElementById('eraser').onclick=function(){tool='eraser';setTool();};
  document.getElementById('undo').onclick=undo;
  document.getElementById('clear').onclick=clearAll;
  document.getElementById('save').onclick=function(){try{AF.saveBlob('canvas',cv.toDataURL('image/png'));}catch(_){}};
  cv.addEventListener('pointerdown',start);cv.addEventListener('pointermove',move);
  window.addEventListener('pointerup',end);window.addEventListener('resize',fit);
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='set_color'){if(args.color){color=args.color;tool='pen';document.getElementById('cp').value=args.color;setTool();}}
    else if(name==='set_size'){if(args.size){size=Math.max(1,Math.min(40,+args.size));document.getElementById('size').value=size;}}
    else if(name==='set_tool'){if(args.tool==='pen'||args.tool==='eraser'){tool=args.tool;setTool();}}
    else if(name==='clear'){clearAll();}
    else if(name==='undo'){undo();}
  };
  fit();
  (async function(){var d=await AF.loadBlob('canvas');if(d){var im=new Image();im.onload=function(){ctx.drawImage(im,0,0);};im.src=d;}})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "paint",
    "title": "ペイント",
    "description": "ペン・消しゴム・カラーパレット・太さ・元に戻す・全消去で自由に描けるお絵描き。絵はこの端末に保存されます。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "set_color", "description": "ペンの色を変更（#RRGGBB）",
         "inputSchema": {"type": "object", "properties": {"color": {"type": "string"}}, "required": ["color"]}},
        {"name": "set_size", "description": "線の太さ(1-40)",
         "inputSchema": {"type": "object", "properties": {"size": {"type": "number"}}, "required": ["size"]}},
        {"name": "set_tool", "description": "pen / eraser を切替",
         "inputSchema": {"type": "object", "properties": {"tool": {"type": "string"}}, "required": ["tool"]}},
        {"name": "clear", "description": "全消去", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "undo", "description": "ひとつ戻す", "inputSchema": {"type": "object", "properties": {}}},
    ],
    "worker_instructions": (
        "ペイント操作用ワーカー。描画ツールの色、太さ、ペン/消しゴム切替、Undo、全消去を担当する。"
        "『赤にして/青で描く』は set_color。『太く/細く』は set_size。『消しゴム』は set_tool。"
        "『戻して』は undo。『全部消して/クリア』は clear。実際に絵を描く線そのものはユーザーの操作対象。"
    ),
    "worker_examples": [
        {"user": "赤にして", "command": {"name": "set_color", "arguments": {"color": "#ef4444"}}, "reply": "ペン色を赤にします。"},
        {"user": "消しゴムにして", "command": {"name": "set_tool", "arguments": {"tool": "eraser"}}, "reply": "消しゴムに切り替えます。"},
        {"user": "全部消して", "command": {"name": "clear", "arguments": {}}, "reply": "キャンバスを全消去します。"},
        {"user": "ひとつ戻して", "command": {"name": "undo", "arguments": {}}, "reply": "ひとつ戻します。"},
    ],
}
