"""Default mini-app template: ペイント (paint)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f3f3f7;--bar:#fff;--panel:#fafafe;--ac:#4f46e5;--bd:#dfe2ee;--fg:#23233a;--mut:#68708a}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg);display:flex;flex-direction:column}
.bar{display:grid;grid-template-columns:auto auto 1fr auto;gap:10px;align-items:start;padding:8px 10px;background:var(--bar);border-bottom:1px solid var(--bd)}
.group{display:flex;align-items:center;gap:6px;padding:6px;border:1px solid var(--bd);border-radius:8px;background:var(--panel);min-height:50px}
.group.colors{display:grid;grid-template-columns:auto auto;gap:7px;align-items:center}.label{font-size:11px;color:var(--mut);font-weight:800;letter-spacing:.02em}
.current{display:grid;grid-template-columns:32px 32px;gap:4px}.chip{width:32px;height:32px;border:1px solid #b9bfd0;background:#fff;border-radius:5px}
.chip.main{box-shadow:inset 0 0 0 3px #fff,0 0 0 1px var(--ac)}.palette{display:grid;grid-template-columns:repeat(12,22px);gap:4px}
.swatch{width:22px;height:22px;border-radius:3px;border:1px solid rgba(0,0,0,.18);box-shadow:inset 0 0 0 1px rgba(255,255,255,.45);cursor:pointer}
.swatch.on{outline:2px solid var(--ac);outline-offset:1px}
.color-tools{display:grid;gap:5px}input[type=color]{width:40px;height:30px;border:1px solid var(--bd);border-radius:6px;background:#fff;padding:2px;cursor:pointer}
.hex{width:82px;border:1px solid var(--bd);border-radius:6px;padding:6px 7px;font:12px ui-monospace,monospace;text-transform:uppercase;color:var(--fg)}
.tool{border:1px solid var(--bd);background:#fff;border-radius:7px;padding:7px 9px;cursor:pointer;font-size:13px;color:var(--fg);white-space:nowrap}
.tool.on{background:var(--ac);color:#fff;border-color:var(--ac)}.tool.icon{min-width:72px;text-align:center}
.sizebox{display:grid;grid-template-columns:auto 104px 34px;gap:6px;align-items:center}.sizebox output{font-size:12px;color:var(--mut);text-align:right}
input[type=range]{width:104px}.actions{justify-content:flex-end}.wrap{flex:1;position:relative;background:#d8dbe6;padding:12px}
canvas{width:100%;height:100%;touch-action:none;background:#fff;display:block;border:1px solid #cfd3df;box-shadow:0 1px 4px rgba(30,34,50,.08);cursor:crosshair}
@media(max-width:760px){.bar{grid-template-columns:1fr}.group{flex-wrap:wrap}.palette{grid-template-columns:repeat(8,22px)}.actions{justify-content:flex-start}}
</style></head><body>
<div class="bar">
  <div class="group colors" aria-label="色">
    <div class="current"><span class="chip main" id="cur"></span><span class="chip" id="prev"></span></div>
    <div class="palette" id="sw"></div>
    <div class="label">色</div>
    <div class="color-tools">
      <input type="color" id="cp" value="#222222" title="色を選ぶ">
      <input class="hex" id="hex" value="#222222" maxlength="7" title="#RRGGBB">
    </div>
  </div>
  <div class="group" aria-label="ペンの種類">
    <button class="tool icon on" data-tool="pen">ペン</button>
    <button class="tool icon" data-tool="pencil">鉛筆</button>
    <button class="tool icon" data-tool="marker">マーカー</button>
    <button class="tool icon" data-tool="spray">スプレー</button>
    <button class="tool icon" data-tool="eraser">消しゴム</button>
  </div>
  <div class="group sizebox" aria-label="太さ">
    <span class="label">太さ</span><input type="range" id="size" min="1" max="48" value="5"><output id="sizeOut">5</output>
  </div>
  <div class="group actions">
    <button class="tool" id="undo">戻す</button>
    <button class="tool" id="clear">全消去</button>
    <button class="tool" id="save">PNGダウンロード</button>
  </div>
</div>
<div class="wrap"><canvas id="cv"></canvas></div>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  var color='#222222',prevColor='#ffffff',size=5,tool='pen',drawing=false,last=null,lastDir=null,brushWidth=0,undoStack=[];
  var PALETTE=[
    '#000000','#404040','#808080','#c0c0c0','#ffffff','#7f1d1d','#dc2626','#f97316','#facc15','#16a34a','#0891b2','#2563eb',
    '#1f2937','#5b6472','#9ca3af','#e5e7eb','#fef2f2','#991b1b','#ef4444','#fb923c','#fde047','#22c55e','#06b6d4','#3b82f6',
    '#312e81','#6d28d9','#a855f7','#ec4899','#f43f5e','#854d0e','#a16207','#4d7c0f','#15803d','#0f766e','#0369a1','#1d4ed8'
  ];
  function fit(){
    var r=cv.parentNode.getBoundingClientRect(),old=document.createElement('canvas'),o=old.getContext('2d');
    old.width=cv.width||1;old.height=cv.height||1;o.drawImage(cv,0,0);
    cv.width=Math.max(320,Math.floor(r.width-24));cv.height=Math.max(220,Math.floor(r.height-24));
    ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);try{ctx.drawImage(old,0,0);}catch(_){}
  }
  function normalizeHex(v){v=String(v||'').trim();if(/^#[0-9a-fA-F]{6}$/.test(v))return v.toLowerCase();return null;}
  function hexToRgba(hex,a){var n=parseInt(hex.slice(1),16);return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')';}
  function setColor(c){c=normalizeHex(c);if(!c)return;prevColor=color;color=c;tool=tool==='eraser'?'pen':tool;syncUi();persistPrefs();}
  function setTool(t){if(['pen','pencil','marker','spray','eraser'].indexOf(t)<0)return;tool=t;syncUi();persistPrefs();}
  function setSize(v){size=Math.max(1,Math.min(48,+v||5));syncUi();persistPrefs();}
  function syncUi(){
    document.getElementById('cur').style.background=color;document.getElementById('prev').style.background=prevColor;
    document.getElementById('cp').value=color;document.getElementById('hex').value=color.toUpperCase();
    document.getElementById('size').value=size;document.getElementById('sizeOut').textContent=size;
    document.querySelectorAll('[data-tool]').forEach(function(b){b.classList.toggle('on',b.getAttribute('data-tool')===tool);});
    document.querySelectorAll('.swatch').forEach(function(s){s.classList.toggle('on',s.getAttribute('data-color')===color);});
  }
  function pushUndo(){try{undoStack.push(cv.toDataURL('image/png'));if(undoStack.length>24)undoStack.shift();}catch(_){}}
  function pos(e){var r=cv.getBoundingClientRect();return {x:(e.clientX-r.left)*(cv.width/r.width),y:(e.clientY-r.top)*(cv.height/r.height)};}
  function dist(a,b){var dx=b.x-a.x,dy=b.y-a.y;return Math.sqrt(dx*dx+dy*dy)||1;}
  function brushStyle(){ctx.lineCap='round';ctx.lineJoin='round';ctx.globalCompositeOperation='source-over';ctx.shadowBlur=0;ctx.globalAlpha=1;ctx.lineWidth=size;ctx.strokeStyle=color;ctx.fillStyle=color;
    if(tool==='eraser'){ctx.globalCompositeOperation='source-over';ctx.strokeStyle='#ffffff';ctx.fillStyle='#ffffff';ctx.lineWidth=size*1.6;}
    else if(tool==='brush'){ctx.lineWidth=size*1.2;ctx.shadowBlur=Math.max(1,size*.18);ctx.shadowColor=color;}
  }
  function stamp(p,r,alpha,fill){ctx.globalAlpha=alpha;ctx.fillStyle=fill||color;ctx.beginPath();ctx.arc(p.x,p.y,Math.max(.7,r),0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}
  function sketchStroke(x1,y1,x2,y2,width,alpha){
    ctx.save();ctx.globalAlpha=alpha;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap='butt';ctx.lineJoin='round';
    ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.restore();
  }
  function pencilLine(a,b){
    var d=dist(a,b),steps=Math.max(1,Math.ceil(d/1.55)),dx=(b.x-a.x)/steps,dy=(b.y-a.y)/steps,base=Math.max(.5,size*.15);
    var nx=-(b.y-a.y)/d,ny=(b.x-a.x)/d;
    for(var i=0;i<=steps;i++){
      if(Math.random()<.06)continue;
      var x=a.x+dx*i,y=a.y+dy*i,j=(Math.random()-.5)*(1.45+size*.18),len=1.25+Math.random()*2.25;
      sketchStroke(x+nx*j-dx*.35,y+ny*j-dy*.35,x+nx*j+dx*len,y+ny*j+dy*len,base*(.78+Math.random()*.62),.38+Math.random()*.24);
      if(Math.random()<.08){
        var j2=(Math.random()-.5)*(3.8+size*.24);
        sketchStroke(x+nx*j2,y+ny*j2,x+nx*j2+dx*(.55+Math.random()),y+ny*j2+dy*(.55+Math.random()),Math.max(.32,base*.48),.06);
      }
    }
  }
  function markerLine(a,b){
    var d=dist(a,b),steps=Math.max(1,Math.ceil(d/3)),dx=(b.x-a.x)/steps,dy=(b.y-a.y)/steps,w=Math.max(5,size*2.35),h=Math.max(2,size*.72),ang=-Math.PI/9;
    ctx.fillStyle=hexToRgba(color,.42);
    for(var i=0;i<=steps;i++){
      var x=a.x+dx*i,y=a.y+dy*i;
      ctx.save();ctx.translate(x,y);ctx.rotate(ang);ctx.fillRect(-w*.28,-h*.5,w*.56,h);ctx.restore();
    }
  }
  function brushLine(a,b){
    var d=dist(a,b),steps=Math.max(1,Math.ceil(d/2.4)),nx=-(b.y-a.y)/d,ny=(b.x-a.x)/d;
    var speedThin=Math.max(.58,Math.min(1.05,18/(d+10))),target=size*(1.18*speedThin+.42);
    if(!brushWidth)brushWidth=target*.92;
    ctx.save();ctx.strokeStyle=color;ctx.lineCap='round';ctx.lineJoin='round';
    for(var i=1;i<=steps;i++){
      var t0=(i-1)/steps,t=i/steps,ease=t*t*(3-2*t);
      var x0=a.x+(b.x-a.x)*t0,y0=a.y+(b.y-a.y)*t0,x1=a.x+(b.x-a.x)*t,y1=a.y+(b.y-a.y)*t;
      var w=brushWidth+(target-brushWidth)*ease*.38;
      ctx.globalAlpha=.66;ctx.lineWidth=w;ctx.beginPath();ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);ctx.stroke();
      ctx.globalAlpha=.12;ctx.lineWidth=Math.max(.75,w*.22);ctx.beginPath();ctx.moveTo(x0+nx*w*.24,y0+ny*w*.24);ctx.lineTo(x1+nx*w*.24,y1+ny*w*.24);ctx.stroke();
      ctx.globalAlpha=.1;ctx.lineWidth=Math.max(.55,w*.16);ctx.beginPath();ctx.moveTo(x0-nx*w*.18,y0-ny*w*.18);ctx.lineTo(x1-nx*w*.18,y1-ny*w*.18);ctx.stroke();
      var fibers=[-.32,-.18,.02,.21,.35];
      for(var f=0;f<fibers.length;f++){
        var fo=fibers[f]*w+(Math.random()-.5)*w*.05,fa=(f%2?-.018:.026);
        ctx.globalAlpha=.045+fa;ctx.lineWidth=Math.max(.32,w*(f%2?.055:.075));
        ctx.beginPath();ctx.moveTo(x0+nx*fo,y0+ny*fo);ctx.lineTo(x1+nx*(fo*.98),y1+ny*(fo*.98));ctx.stroke();
      }
      if(i%2===0){
        var off=(Math.random()-.5)*w*.42;
        ctx.globalAlpha=.09;ctx.lineWidth=Math.max(.45,w*.1);ctx.beginPath();ctx.moveTo(x0+nx*off,y0+ny*off);ctx.lineTo(x1+nx*(off*.8),y1+ny*(off*.8));ctx.stroke();
      }
    }
    brushWidth+= (target-brushWidth)*.14;
    ctx.restore();
  }
  function brushFlick(){
    if(tool!=='brush'||!lastDir)return;
    var base=brushWidth||size*.75,back=Math.min(size*4.2,Math.max(size*1.5,lastDir.d*1.05));
    var start={x:lastDir.to.x-lastDir.x*back,y:lastDir.to.y-lastDir.y*back},end={x:lastDir.to.x,y:lastDir.to.y};
    ctx.save();ctx.strokeStyle=color;ctx.lineCap='round';ctx.lineJoin='round';
    for(var i=0;i<7;i++){
      var t0=i/7,t1=(i+1)/7,e0=t0*t0*(3-2*t0),e1=t1*t1*(3-2*t1);
      var x0=start.x+(end.x-start.x)*t0,y0=start.y+(end.y-start.y)*t0,x1=start.x+(end.x-start.x)*t1,y1=start.y+(end.y-start.y)*t1;
      ctx.globalAlpha=.36*(1-e0)+.035;ctx.lineWidth=Math.max(.35,base*(.58*(1-e1)+.045));
      ctx.beginPath();ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);ctx.stroke();
      var off=(Math.random()-.5)*base*.38;
      ctx.globalAlpha=.13*(1-e0)+.018;ctx.lineWidth=Math.max(.25,base*(.13*(1-e1)+.02));
      ctx.beginPath();ctx.moveTo(x0-lastDir.y*off,y0+lastDir.x*off);ctx.lineTo(x1-lastDir.y*off*.65,y1+lastDir.x*off*.65);ctx.stroke();
    }
    ctx.restore();
  }
  function drawDot(p){if(tool==='spray'){spray(p);return;}if(tool==='pencil'){pencilLine({x:p.x-.8,y:p.y-.2},{x:p.x+1.2,y:p.y+.3});return;}if(tool==='marker'){markerLine(p,{x:p.x+.5,y:p.y+.5});return;}if(tool==='brush'){brushWidth=size*.82;brushLine({x:p.x-size*.28,y:p.y-size*.08},{x:p.x+size*.28,y:p.y+size*.08});return;}brushStyle();ctx.beginPath();ctx.arc(p.x,p.y,Math.max(1,ctx.lineWidth/2),0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;ctx.shadowBlur=0;}
  function drawLine(a,b){var d=dist(a,b);lastDir={x:(b.x-a.x)/d,y:(b.y-a.y)/d,d:d,to:b,from:a};if(tool==='spray'){spray(b);return;}if(tool==='pencil'){pencilLine(a,b);return;}if(tool==='marker'){markerLine(a,b);return;}if(tool==='brush'){brushLine(a,b);return;}brushStyle();ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.globalAlpha=1;ctx.shadowBlur=0;}
  function spray(p){var radius=size*1.3,dots=Math.max(8,Math.round(size*1.2));ctx.fillStyle=tool==='eraser'?'#fff':color;ctx.globalAlpha=tool==='eraser'?1:.45;
    for(var i=0;i<dots;i++){var ang=Math.random()*Math.PI*2,dist=Math.random()*radius;ctx.fillRect(p.x+Math.cos(ang)*dist,p.y+Math.sin(ang)*dist,1.6,1.6);}ctx.globalAlpha=1;}
  function start(e){e.preventDefault();pushUndo();drawing=true;last=pos(e);lastDir=null;brushWidth=0;drawDot(last);}
  function move(e){if(!drawing)return;e.preventDefault();var p=pos(e);drawLine(last,p);last=p;}
  function end(){if(!drawing)return;brushFlick();drawing=false;last=null;lastDir=null;brushWidth=0;persistCanvas();}
  var saveCanvasT,savePrefsT;
  function persistCanvas(){clearTimeout(saveCanvasT);saveCanvasT=setTimeout(function(){try{AF.saveBlob('canvas',cv.toDataURL('image/png'));}catch(_){}},500);}
  function persistPrefs(){clearTimeout(savePrefsT);savePrefsT=setTimeout(function(){try{AF.save({color:color,prevColor:prevColor,size:size,tool:tool});}catch(_){}},200);}
  function clearAll(){pushUndo();ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);persistCanvas();}
  function undo(){var d=undoStack.pop();if(!d)return;var im=new Image();im.onload=function(){ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);ctx.drawImage(im,0,0);persistCanvas();};im.src=d;}
  var swEl=document.getElementById('sw');PALETTE.forEach(function(c){var s=document.createElement('button');s.type='button';s.className='swatch';s.setAttribute('data-color',c);s.title=c;s.style.background=c;s.onclick=function(){setColor(c);};swEl.appendChild(s);});
  document.getElementById('cp').oninput=function(e){setColor(e.target.value);};
  document.getElementById('hex').onchange=function(e){var c=normalizeHex(e.target.value);if(c)setColor(c);else syncUi();};
  document.getElementById('prev').onclick=function(){setColor(prevColor);};
  document.getElementById('size').oninput=function(e){setSize(e.target.value);};
  document.querySelectorAll('[data-tool]').forEach(function(b){b.onclick=function(){setTool(b.getAttribute('data-tool'));};});
  document.getElementById('undo').onclick=undo;document.getElementById('clear').onclick=clearAll;
  function downloadPng(){
    try{
      var a=document.createElement('a'),ts=new Date().toISOString().replace(/[:.]/g,'-');
      a.href=cv.toDataURL('image/png');a.download='agentforge-paint-'+ts+'.png';
      document.body.appendChild(a);a.click();a.remove();
    }catch(_){}
  }
  document.getElementById('save').onclick=function(){downloadPng();persistCanvas();persistPrefs();};
  cv.addEventListener('pointerdown',start);cv.addEventListener('pointermove',move);window.addEventListener('pointerup',end);window.addEventListener('resize',fit);
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='set_color'){setColor(args.color);}
    else if(name==='set_size'){setSize(args.size);}
    else if(name==='set_tool'){setTool(args.tool);}
    else if(name==='clear'){clearAll();}
    else if(name==='undo'){undo();}
  };
  fit();syncUi();
  (async function(){
    try{var prefs=await AF.load();if(prefs){color=normalizeHex(prefs.color)||color;prevColor=normalizeHex(prefs.prevColor)||prevColor;size=Math.max(1,Math.min(48,+prefs.size||size));if(prefs.tool)setTool(prefs.tool);syncUi();}}catch(_){}
    try{var d=await AF.loadBlob('canvas');if(d){var im=new Image();im.onload=function(){ctx.drawImage(im,0,0,cv.width,cv.height);};im.src=d;}}catch(_){}
  })();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "paint",
    "title": "ペイント",
    "description": "Windows ペイント風の色パレット、カスタム色、複数のペン種類、太さ、元に戻す、全消去で自由に描けるお絵描き。描いた絵は PNG としてダウンロードできます。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "set_color", "description": "ペンの色を変更（#RRGGBB）",
         "inputSchema": {"type": "object", "properties": {"color": {"type": "string"}}, "required": ["color"]}},
        {"name": "set_size", "description": "線の太さ(1-48)",
         "inputSchema": {"type": "object", "properties": {"size": {"type": "number"}}, "required": ["size"]}},
        {"name": "set_tool", "description": "pen / pencil / marker / spray / eraser を切替",
         "inputSchema": {"type": "object", "properties": {"tool": {"type": "string"}}, "required": ["tool"]}},
        {"name": "clear", "description": "全消去", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "undo", "description": "ひとつ戻す", "inputSchema": {"type": "object", "properties": {}}},
    ],
    "worker_instructions": (
        "ペイント操作用ワーカー。描画ツールの色、太さ、ペン種類（pen/pencil/marker/spray/eraser）、"
        "Undo、全消去を担当する。『赤にして/青で描く』は set_color。『太く/細く』は set_size。"
        "『鉛筆/マーカー/スプレー/消しゴム』は set_tool。『戻して』は undo。"
        "『全部消して/クリア』は clear。実際に絵を描く線そのものはユーザーの操作対象。"
    ),
    "worker_examples": [
        {"user": "赤にして", "command": {"name": "set_color", "arguments": {"color": "#ef4444"}}, "reply": "ペン色を赤にします。"},
        {"user": "マーカーにして", "command": {"name": "set_tool", "arguments": {"tool": "marker"}}, "reply": "マーカーに切り替えます。"},
        {"user": "スプレーを使いたい", "command": {"name": "set_tool", "arguments": {"tool": "spray"}}, "reply": "スプレーに切り替えます。"},
        {"user": "消しゴムにして", "command": {"name": "set_tool", "arguments": {"tool": "eraser"}}, "reply": "消しゴムに切り替えます。"},
        {"user": "全部消して", "command": {"name": "clear", "arguments": {}}, "reply": "キャンバスを全消去します。"},
        {"user": "ひとつ戻して", "command": {"name": "undo", "arguments": {}}, "reply": "ひとつ戻します。"},
    ],
}
