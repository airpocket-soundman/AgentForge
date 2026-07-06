"""Default mini-app template: レタッチスタジオ (retouch).

Layers live as decoded canvases in memory (PNG-encoding happens only when the
project is saved), so brush strokes, drags and filters run synchronously — the
previous data-URL round trip per stroke segment made drawing unusably laggy.
"""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef1f6;--panel:#ffffff;--ink:#172033;--mut:#677089;--line:#d9deea;--ac:#2563eb;--soft:#f7f9fd}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--ink)}
.app{height:100%;display:grid;grid-template-columns:280px 1fr 260px;grid-template-rows:auto 1fr;gap:10px;padding:10px}
.top{grid-column:1/4;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button,.filebtn{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:7px;padding:8px 10px;font-weight:700;font-size:13px;cursor:pointer}
button.primary,.filebtn.primary{background:var(--ac);border-color:var(--ac);color:#fff}button:disabled{opacity:.45;cursor:not-allowed}button.active{background:#dbeafe;border-color:#60a5fa;color:#1d4ed8}
.filebtn input{display:none}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;min-height:0;overflow:hidden}
.left,.right{display:flex;flex-direction:column}.panel h2{font-size:14px;margin:0;padding:12px;border-bottom:1px solid var(--line)}
.hint{font-size:12px;color:var(--mut);line-height:1.5}.toolbox{padding:10px;display:grid;gap:8px;overflow:auto}.toolbox label{display:grid;gap:5px;font-size:12px;color:var(--mut);font-weight:700}
input[type=range]{width:100%}.workspace{position:relative;overflow:auto;background:#dfe3ec;border-radius:8px;border:1px solid var(--line)}
.stagewrap{min-width:100%;min-height:100%;display:grid;place-items:center;padding:28px}
.stage{position:relative;box-shadow:0 10px 30px rgba(23,32,51,.18);background-image:linear-gradient(45deg,#ccd2df 25%,transparent 25%),linear-gradient(-45deg,#ccd2df 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ccd2df 75%),linear-gradient(-45deg,transparent 75%,#ccd2df 75%);background-size:22px 22px;background-position:0 0,0 11px,11px -11px,-11px 0}
canvas{display:block;max-width:none;touch-action:none}.empty{padding:24px;max-width:520px;text-align:center;background:rgba(255,255,255,.86);border:1px dashed #aeb7c8;border-radius:8px}
.layers{list-style:none;margin:0;padding:8px;overflow:auto;flex:1}.layers li{display:grid;grid-template-columns:20px 48px 1fr;gap:8px;align-items:center;padding:7px;border:1px solid var(--line);border-radius:8px;margin-bottom:7px;background:var(--soft);cursor:pointer}
.layers li.on{border-color:var(--ac);box-shadow:0 0 0 2px rgba(37,99,235,.12);background:#eef5ff}.lname{font-weight:800;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lmeta{font-size:11px;color:var(--mut)}
.thumb{width:44px;height:34px;border:1px solid var(--line);border-radius:4px;background:repeating-conic-gradient(#e5e9f2 0 25%,#fff 0 50%) 0 0/12px 12px}
.eye{width:18px;height:18px}.mini{font-size:12px;padding:5px 7px}.row{display:flex;gap:6px;flex-wrap:wrap}
.lactions{display:flex;gap:5px;flex-wrap:wrap;padding:8px;border-top:1px solid var(--line)}
.sep{width:1px;height:22px;background:var(--line)}.grow{flex:1}
.zoombox{display:flex;align-items:center;gap:4px}#zoomLabel{min-width:46px;text-align:center;font-size:12px;font-weight:700;color:var(--mut)}
.status{padding:9px 10px;border-top:1px solid var(--line);font-size:12px;color:var(--mut);min-height:36px}.danger{color:#b42318}
@media(max-width:880px){.app{grid-template-columns:1fr;grid-template-rows:auto auto minmax(300px,1fr) auto}.top,.left,.workspace,.right{grid-column:1}.left,.right{max-height:230px}.right .toolbox{max-height:170px}}
</style></head><body>
<div class="app">
  <div class="top">
    <label class="filebtn primary">画像を開く<input id="file" type="file" accept="image/*"></label>
    <span class="sep"></span>
    <button id="undo" title="Ctrl+Z">↩ Undo</button><button id="redo" title="Ctrl+Y">↪ Redo</button>
    <span class="sep"></span>
    <div class="zoombox">
      <button id="zoomOut" class="mini" title="縮小">−</button>
      <span id="zoomLabel">100%</span>
      <button id="zoomIn" class="mini" title="拡大">＋</button>
      <button id="zoomFit" class="mini">フィット</button>
      <button id="zoom100" class="mini">100%</button>
    </div>
    <span class="grow"></span>
    <button id="download" class="primary">PNGダウンロード</button>
  </div>
  <section class="panel left">
    <h2>レイヤ</h2>
    <ul class="layers" id="layers"></ul>
    <div class="lactions">
      <button id="blank" class="mini">空レイヤ</button><button id="dup" class="mini">複製</button><button id="del" class="mini">削除</button>
      <button id="up" class="mini">上へ</button><button id="down" class="mini">下へ</button>
    </div>
    <div class="status" id="status">画像を開くと編集できます。</div>
  </section>
  <main class="workspace" id="ws">
    <div class="stagewrap"><div class="stage" id="stage"><canvas id="view"></canvas><div class="empty" id="empty"><b>レタッチスタジオ</b><p class="hint">「画像を開く」のほか、この領域への<b>ドラッグ&ドロップ</b>や <b>Ctrl+V 貼り付け</b>でも読み込めます。レイヤ管理、ブラシ/消しゴム、背景削除、透過、明るさ/コントラスト補正、切り抜きをブラウザ内で実行します。</p></div></div></div>
  </main>
  <section class="panel right">
    <h2>ツール・処理</h2>
    <div class="toolbox">
      <div class="row">
        <button id="toolMove" class="active" title="V">移動</button>
        <button id="toolBrush" title="B">ブラシ</button>
        <button id="toolEraser" title="E">消しゴム</button>
        <button id="toolSelect" title="W">選択</button>
      </div>
      <label>ブラシ色 <input type="color" id="brushColor" value="#111827"></label>
      <label>ブラシサイズ <input type="range" id="brushSize" min="2" max="90" value="22"></label>
      <label>不透明度（選択レイヤ） <input type="range" id="opacity" min="0" max="100" value="100"></label>
      <label>しきい値（選択・背景削除・透過） <input type="range" id="threshold" min="5" max="140" value="42"></label>
      <label>明るさ <input type="range" id="brightness" min="-80" max="80" value="0"></label>
      <label>コントラスト <input type="range" id="contrast" min="-80" max="80" value="0"></label>
      <label>透過色 <input type="color" id="keycolor" value="#ffffff"></label>
      <div class="row">
        <button id="removeBg">背景削除</button>
        <button id="outline">輪郭抽出</button>
        <button id="transparent">透過処理</button>
        <button id="adjust">補正適用</button>
      </div>
      <div class="row">
        <button id="delOutside">選択以外を透過</button>
        <button id="expandSel">選択を広げる</button>
        <button id="clearSel">選択解除</button>
      </div>
      <div class="row">
        <button id="clearLayer">レイヤ消去</button>
        <button id="crop">切り抜き</button>
      </div>
      <p class="hint">「選択」ツール: クリックでオブジェクトの境界を検出、<b>ドラッグでおおよそ囲むと近くの境界にスナップ</b>して選択します。クリック/ドラッグを重ねると選択が増え、つながった部分は1つのオブジェクトとして境界を保持。Alt+クリックで部分解除、「選択を広げる」で縁の取りこぼしと穴を吸収、「選択以外を透過」で背景を消せます。ショートカット: Ctrl+Z 取り消し / Ctrl+Y やり直し / V 移動 / B ブラシ / E 消しゴム / W 選択 / Esc 選択解除 / Ctrl+ホイール ズーム。破壊的な処理は Undo で戻せます。</p>
    </div>
  </section>
</div>
<script>
(function(){
  var $=function(id){return document.getElementById(id);};
  var view=$('view'),vctx=view.getContext('2d'),stage=$('stage'),ws=$('ws');
  // Layers hold DECODED canvases (l.c). PNG data URLs exist only in saved
  // projects — never in the hot path (the old per-segment decode/encode cycle
  // is what made drawing lag).
  var layers=[],activeId=null,w=900,h=560,zoom=1,seq=1,saveT=null,metaT=null,tool='move',drawing=false,lastPt=null,dragStart=null,undoStack=[],redoStack=[],raf=0;
  var MAX_HISTORY=12;
  // Click-to-select (magic wand): a pixel mask on ONE layer. Each click flood-
  // fills the clicked object and UNIONs it into the mask, so touching objects
  // merge into one region whose single boundary is drawn on the composite.
  // Dragging the select tool traces a rough area that SNAPS to nearby edges.
  var sel=null,selLayerId=null,selEdge=[];
  var tracing=false,tracePts=[],traceAlt=false;
  function id(){return 'layer_'+Date.now().toString(36)+'_'+(seq++);}
  function byId(lid){return layers.find(function(l){return l.id===lid;})||null;}
  function active(){return byId(activeId)||layers[layers.length-1]||null;}
  function msg(t,bad){var e=$('status');e.textContent=t;e.className='status'+(bad?' danger':'');}
  function makeCanvas(cw,ch){var c=document.createElement('canvas');c.width=cw||w;c.height=ch||h;return c;}
  function copyCanvas(c){var n=makeCanvas(c.width,c.height);n.getContext('2d').drawImage(c,0,0);return n;}
  function layerFrom(c,name){return {id:id(),name:name||('レイヤ '+seq),visible:true,opacity:1,x:0,y:0,c:c};}

  // --- History: cheap per-kind snapshots instead of full base64 clones -------
  // 'pix'  = one layer's pixels+position (strokes, filters, clear)
  // 'meta' = names/visibility/opacity/positions/order (rename, reorder, move)
  // 'full' = everything incl. canvas size (add/delete/duplicate/crop)
  function snapPix(l){return {t:'pix',id:l.id,c:copyCanvas(l.c),x:l.x||0,y:l.y||0};}
  function snapMeta(){return {t:'meta',activeId:activeId,metas:layers.map(function(l){return {id:l.id,name:l.name,visible:l.visible,opacity:l.opacity,x:l.x||0,y:l.y||0};})};}
  function snapFull(){return {t:'full',w:w,h:h,activeId:activeId,layers:layers.map(function(l){return {id:l.id,name:l.name,visible:l.visible,opacity:l.opacity,x:l.x||0,y:l.y||0,c:copyCanvas(l.c)};})};}
  function currentLike(e){if(e.t==='pix'){var l=byId(e.id);return l?snapPix(l):snapFull();}return e.t==='meta'?snapMeta():snapFull();}
  function applySnap(e){
    if(e.t==='pix'){var l=byId(e.id);if(l){l.c=copyCanvas(e.c);l.x=e.x;l.y=e.y;}}
    else if(e.t==='meta'){
      var order=[];
      e.metas.forEach(function(m){var l=byId(m.id);if(!l)return;l.name=m.name;l.visible=m.visible;l.opacity=m.opacity;l.x=m.x;l.y=m.y;order.push(l);});
      layers.forEach(function(l){if(order.indexOf(l)<0)order.push(l);});
      layers=order;activeId=e.activeId||activeId;
    }else{
      w=e.w;h=e.h;activeId=e.activeId;
      layers=e.layers.map(function(l){return {id:l.id,name:l.name,visible:l.visible,opacity:l.opacity,x:l.x,y:l.y,c:copyCanvas(l.c)};});
    }
    clearSelection(); // pixels/structure changed — the selection mask is stale
    syncControls();render();renderLayers();saveSoon();
  }
  function pushHistory(entry){undoStack.push(entry);if(undoStack.length>MAX_HISTORY)undoStack.shift();redoStack=[];}
  function undo(){if(!undoStack.length)return msg('戻せる操作がありません。',true);var e=undoStack.pop();redoStack.push(currentLike(e));applySnap(e);msg('直前の操作を戻しました。');}
  function redo(){if(!redoStack.length)return msg('やり直せる操作がありません。',true);var e=redoStack.pop();undoStack.push(currentLike(e));applySnap(e);msg('操作をやり直しました。');}

  // --- Rendering (synchronous composite + rAF throttle) ----------------------
  function applyView(){
    view.width=w;view.height=h;
    var dw=Math.max(1,Math.round(w*zoom)),dh=Math.max(1,Math.round(h*zoom));
    view.style.width=dw+'px';view.style.height=dh+'px';stage.style.width=dw+'px';stage.style.height=dh+'px';
    $('zoomLabel').textContent=Math.round(zoom*100)+'%';
  }
  function render(){
    applyView();vctx.clearRect(0,0,w,h);
    layers.forEach(function(l){if(!l.visible)return;vctx.globalAlpha=l.opacity;vctx.drawImage(l.c,l.x||0,l.y||0);vctx.globalAlpha=1;});
    drawSelection();
    drawTrace();
    $('empty').style.display=layers.length?'none':'block';
  }
  function drawTrace(){
    if(!tracing||tracePts.length<2)return;
    vctx.save();
    vctx.strokeStyle='#2563eb';vctx.lineWidth=Math.max(1,1.5/zoom);vctx.setLineDash([4,3]);
    vctx.beginPath();vctx.moveTo(tracePts[0].x,tracePts[0].y);
    for(var i=1;i<tracePts.length;i++)vctx.lineTo(tracePts[i].x,tracePts[i].y);
    vctx.stroke();vctx.restore();
  }
  function drawSelection(){
    if(!sel||!selEdge.length)return;
    var l=byId(selLayerId);if(!l)return;
    var ox=l.x||0,oy=l.y||0,cw=l.c.width;
    for(var i=0;i<selEdge.length;i++){
      var p=selEdge[i],x=p%cw,y=(p-x)/cw;
      vctx.fillStyle=(((x+y)>>2)&1)?'#111827':'#ffffff';
      vctx.fillRect(x+ox,y+oy,1,1);
    }
  }
  function requestRender(){if(raf)return;raf=requestAnimationFrame(function(){raf=0;render();});}
  function renderLayers(){
    var ul=$('layers');ul.innerHTML='';
    layers.slice().reverse().forEach(function(l){
      var li=document.createElement('li');li.className=l.id===activeId?'on':'';
      var eye=document.createElement('input');eye.type='checkbox';eye.className='eye';eye.checked=l.visible;
      var t=makeCanvas(44,34);t.className='thumb';
      var s=Math.min(44/l.c.width,34/l.c.height);
      t.getContext('2d').drawImage(l.c,(44-l.c.width*s)/2,(34-l.c.height*s)/2,l.c.width*s,l.c.height*s);
      var box=document.createElement('div');
      var nm=document.createElement('div');nm.className='lname';nm.textContent=l.name;
      var mt=document.createElement('div');mt.className='lmeta';mt.textContent=Math.round(l.opacity*100)+'% / x'+Math.round(l.x||0)+' y'+Math.round(l.y||0);
      box.appendChild(nm);box.appendChild(mt);
      li.appendChild(eye);li.appendChild(t);li.appendChild(box);
      li.onclick=function(){activeId=l.id;syncControls();renderLayers();};
      eye.onclick=function(e){e.stopPropagation();l.visible=eye.checked;render();saveSoon();};
      ul.appendChild(li);
    });
  }
  function syncControls(){var l=active();$('opacity').value=l?Math.round(l.opacity*100):100;}

  // --- Zoom -------------------------------------------------------------------
  function setZoom(z){zoom=Math.max(0.05,Math.min(4,+z||1));render();saveMetaSoon();}
  function zoomBy(f){setZoom(zoom*f);}
  function fitZoom(){var z=Math.min((ws.clientWidth-56)/w,(ws.clientHeight-56)/h);setZoom(Math.min(1,z));}

  function setTool(t){
    tool=t;
    ['Move','Brush','Eraser','Select'].forEach(function(n){$('tool'+n).classList.toggle('active',tool===n.toLowerCase());});
    view.style.cursor=tool==='move'?'grab':'crosshair';
    saveMetaSoon();
  }

  // --- Layer ops ---------------------------------------------------------------
  function addLayerFromImage(img,name){
    pushHistory(snapFull());
    var nw=img.naturalWidth||img.width||900,nh=img.naturalHeight||img.height||560;
    var sc=Math.min(1,1800/nw,1200/nh);
    var iw=Math.max(1,Math.round(nw*sc)),ih=Math.max(1,Math.round(nh*sc));
    if(!layers.length){w=Math.max(320,iw);h=Math.max(240,ih);}
    var c=makeCanvas(iw,ih);c.getContext('2d').drawImage(img,0,0,iw,ih);
    var l=layerFrom(c,name||('画像 '+seq));layers.push(l);activeId=l.id;
    msg('画像を読み込みました。');fitZoom();render();renderLayers();saveSoon();
  }
  function loadImageFile(f){
    if(!f||String(f.type||'').indexOf('image/')!==0)return;
    var r=new FileReader();
    r.onload=function(){var im=new Image();im.onload=function(){addLayerFromImage(im,f.name||'画像');};im.src=String(r.result);};
    r.readAsDataURL(f);
  }
  function addBlank(name){pushHistory(snapFull());var l=layerFrom(makeCanvas(),name||('空レイヤ '+seq));layers.push(l);activeId=l.id;msg('空レイヤを追加しました。');render();renderLayers();saveSoon();}
  function duplicate(){var l=active();if(!l)return msg('複製するレイヤがありません。',true);pushHistory(snapFull());var n=layerFrom(copyCanvas(l.c),l.name+' コピー');n.visible=l.visible;n.opacity=l.opacity;n.x=l.x||0;n.y=l.y||0;layers.push(n);activeId=n.id;render();renderLayers();saveSoon();}
  function findLayer(args){
    args=args||{};
    if(args.layer_id)return byId(args.layer_id);
    if(args.layer_name)return layers.find(function(l){return l.name===args.layer_name;})||null;
    return active();
  }
  function selectLayer(args){var l=findLayer(args);if(!l)return msg('指定されたレイヤがありません。',true);activeId=l.id;syncControls();renderLayers();saveMetaSoon();msg('レイヤを選択しました。');}
  function renameLayer(args){var l=findLayer(args);if(!l)return msg('名前を変えるレイヤがありません。',true);var name=String(args.name||'').trim();if(!name)return msg('新しいレイヤ名を指定してください。',true);pushHistory(snapMeta());l.name=name;renderLayers();saveSoon();msg('レイヤ名を変更しました。');}
  function removeLayer(args){var l=findLayer(args);if(!l)return msg('削除するレイヤがありません。',true);pushHistory(snapFull());layers=layers.filter(function(x){return x.id!==l.id;});activeId=layers.length?layers[layers.length-1].id:null;if(selLayerId===l.id)clearSelection();render();renderLayers();saveSoon();}
  function clearLayer(){var l=active();if(!l)return msg('消去するレイヤがありません。',true);pushHistory(snapPix(l));l.c.getContext('2d').clearRect(0,0,l.c.width,l.c.height);if(selLayerId===l.id)clearSelection();render();renderLayers();saveSoon();msg('現在のレイヤを消去しました。');}
  function move(dir){var l=active();if(!l)return;var i=layers.indexOf(l),j=i+dir;if(j<0||j>=layers.length)return;pushHistory(snapMeta());layers[i]=layers[j];layers[j]=l;render();renderLayers();saveSoon();}
  function moveActiveLayer(dx,dy){var l=active();if(!l)return msg('移動するレイヤがありません。',true);pushHistory(snapMeta());l.x=(l.x||0)+(+dx||0);l.y=(l.y||0)+(+dy||0);render();renderLayers();saveSoon();}

  // --- Pixel filters (operate directly on the layer canvas — no decode) --------
  function parseHex(hex){var n=parseInt(String(hex).replace('#',''),16);return [(n>>16)&255,(n>>8)&255,n&255];}
  function dist(r,g,b,c){var dr=r-c[0],dg=g-c[1],db=b-c[2];return Math.sqrt(dr*dr+dg*dg+db*db);}
  function corners(data,cw,ch){var pts=[[0,0],[cw-1,0],[0,ch-1],[cw-1,ch-1]],r=0,g=0,b=0,n=0;pts.forEach(function(p){var i=(p[1]*cw+p[0])*4;if(data[i+3]>0){r+=data[i];g+=data[i+1];b+=data[i+2];n++;}});return n?[r/n,g/n,b/n]:[255,255,255];}
  function mutateActive(fn,label){
    var l=active();if(!l)return msg('処理するレイヤがありません。',true);
    pushHistory(snapPix(l));
    var x=l.c.getContext('2d'),im=x.getImageData(0,0,l.c.width,l.c.height);
    fn(im.data,l.c.width,l.c.height);x.putImageData(im,0,0);
    if(selLayerId===l.id)clearSelection();
    msg(label);render();renderLayers();saveSoon();
  }
  function removeBackground(th){mutateActive(function(d,cw,ch){var c=corners(d,cw,ch);for(var i=0;i<d.length;i+=4){if(d[i+3]&&dist(d[i],d[i+1],d[i+2],c)<th)d[i+3]=0;}},'背景に近い色を透明化しました。');}
  function transparentColor(hex,th){var c=parseHex(hex);mutateActive(function(d){for(var i=0;i<d.length;i+=4){if(d[i+3]&&dist(d[i],d[i+1],d[i+2],c)<th)d[i+3]=0;}},'指定色を透明化しました。');}
  function adjustActive(br,ct){mutateActive(function(d){var b=+br||0,c=1+(+ct||0)/100;for(var i=0;i<d.length;i+=4){d[i]=Math.max(0,Math.min(255,(d[i]-128)*c+128+b));d[i+1]=Math.max(0,Math.min(255,(d[i+1]-128)*c+128+b));d[i+2]=Math.max(0,Math.min(255,(d[i+2]-128)*c+128+b));}},'明るさとコントラストを適用しました。');}
  function extractOutline(th){
    var l=active();if(!l)return msg('輪郭抽出するレイヤがありません。',true);
    var cw=l.c.width,ch=l.c.height,src=l.c.getContext('2d').getImageData(0,0,cw,ch).data;
    var out=makeCanvas(cw,ch),ox=out.getContext('2d'),img=ox.createImageData(cw,ch),dst=img.data;
    function lum(p){return src[p+3]===0?0:(src[p]*.299+src[p+1]*.587+src[p+2]*.114)*(src[p+3]/255);}
    for(var y=1;y<ch-1;y++)for(var x=1;x<cw-1;x++){var p=(y*cw+x)*4,a=src[p+3];if(a<8)continue;var gx=Math.abs(lum(p+4)-lum(p-4)),gy=Math.abs(lum(p+cw*4)-lum(p-cw*4));var edge=gx+gy>th||src[p-4+3]<12||src[p+4+3]<12||src[p-cw*4+3]<12||src[p+cw*4+3]<12;if(edge){dst[p]=20;dst[p+1]=24;dst[p+2]=32;dst[p+3]=230;}}
    pushHistory(snapFull());ox.putImageData(img,0,0);
    var nl=layerFrom(out,'輪郭 '+seq);nl.x=l.x||0;nl.y=l.y||0;layers.push(nl);activeId=nl.id;
    msg('輪郭レイヤを作成しました。');render();renderLayers();saveSoon();
  }
  function cropToContent(){
    if(!layers.length)return msg('切り抜く画像がありません。',true);
    render();
    var d=vctx.getImageData(0,0,w,h).data,minX=w,minY=h,maxX=-1,maxY=-1;
    for(var y=0;y<h;y++)for(var x=0;x<w;x++){var a=d[(y*w+x)*4+3];if(a>8){if(x<minX)minX=x;if(y<minY)minY=y;if(x>maxX)maxX=x;if(y>maxY)maxY=y;}}
    if(maxX<0)return msg('不透明な範囲がありません。',true);
    pushHistory(snapFull());
    var nw=maxX-minX+1,nh=maxY-minY+1;
    layers.forEach(function(l){var nc=makeCanvas(nw,nh);nc.getContext('2d').drawImage(l.c,(l.x||0)-minX,(l.y||0)-minY);l.c=nc;l.x=0;l.y=0;});
    w=nw;h=nh;
    clearSelection();
    msg('透明部分を除いて切り抜きました。');fitZoom();render();renderLayers();saveSoon();
  }

  // --- Click-to-select (magic wand) --------------------------------------------
  function clearSelection(){sel=null;selLayerId=null;selEdge=[];}
  function floodAdd(d,cw,ch,sx,sy,th,erase){
    // BFS flood fill; unions into `sel` (or clears when erase). A pixel joins
    // when close to the SEED color, or (half tolerance) to the neighbor that
    // admitted it — so soft gradients inside one object are followed without
    // leaking across hard edges.
    var q=(sy*cw+sx)*4;
    if(d[q+3]<8)return false; // transparent seed = no object under the click
    var sr=d[q],sg=d[q+1],sb=d[q+2],t2=th*th,n2=(th*0.5)*(th*0.5),v=erase?0:1;
    var seen=new Uint8Array(cw*ch),stack=[sx,sy];
    seen[sy*cw+sx]=1;sel[sy*cw+sx]=v;
    while(stack.length){
      var y=stack.pop(),x=stack.pop(),p=y*cw+x,i=p*4;
      var nbs=[x-1,y,x+1,y,x,y-1,x,y+1];
      for(var k=0;k<8;k+=2){
        var nx=nbs[k],ny=nbs[k+1];
        if(nx<0||ny<0||nx>=cw||ny>=ch)continue;
        var np=ny*cw+nx;
        if(seen[np])continue;seen[np]=1;
        var j=np*4;
        if(d[j+3]<8)continue;
        var dr=d[j]-sr,dg=d[j+1]-sg,db=d[j+2]-sb;
        var er=d[j]-d[i],eg=d[j+1]-d[i+1],eb=d[j+2]-d[i+2];
        if(dr*dr+dg*dg+db*db>t2&&er*er+eg*eg+eb*eb>n2)continue;
        sel[np]=v;stack.push(nx,ny);
      }
    }
    return true;
  }
  function maskBoundary(mask,cw,ch){
    var pts=[];
    for(var y=0;y<ch;y++)for(var x=0;x<cw;x++){
      var p=y*cw+x;if(!mask[p])continue;
      if(x===0||y===0||x===cw-1||y===ch-1||!mask[p-1]||!mask[p+1]||!mask[p-cw]||!mask[p+cw])pts.push(p);
    }
    return pts;
  }
  function ensureSelFor(l){
    if(!sel||selLayerId!==l.id||sel.length!==l.c.width*l.c.height){clearSelection();sel=new Uint8Array(l.c.width*l.c.height);selLayerId=l.id;}
  }
  function selCount(){var n=0;for(var i=0;i<sel.length;i++)n+=sel[i];return n;}
  function afterSelChange(note){
    var l=byId(selLayerId);
    selEdge=maskBoundary(sel,l.c.width,l.c.height);
    var count=selCount();
    if(!count){clearSelection();msg('選択が空になりました。',true);render();return;}
    msg('選択範囲: 約'+count.toLocaleString()+'px。'+(note||'')+'「選択以外を透過」で背景を消せます。');
    render();
  }
  function selectObjectAt(pt,th,erase){
    var l=active();if(!l)return msg('選択できるレイヤがありません。画像を開いてください。',true);
    var cw=l.c.width,ch=l.c.height;
    var x=Math.round(pt.x-(l.x||0)),y=Math.round(pt.y-(l.y||0));
    if(x<0||y<0||x>=cw||y>=ch)return msg('レイヤの範囲外です。オブジェクトの上をクリックしてください。',true);
    if(erase&&(!sel||selLayerId!==l.id))return msg('解除できる選択がありません。',true);
    ensureSelFor(l);
    var d=l.c.getContext('2d').getImageData(0,0,cw,ch).data;
    if(!floodAdd(d,cw,ch,x,y,+th||+$('threshold').value||42,erase))
      return msg('透明な場所は選択できません。オブジェクトの上をクリックしてください。',true);
    afterSelChange(erase?'Alt+クリックで解除できます。':'クリックで追加、ドラッグでおおよそ囲むと近くの境界にスナップします。');
  }
  function fillPolygon(pts,cw,ch){
    // Even-odd scanline fill of the (auto-closed) traced path, clipped to the layer.
    if(pts.length<3)return null;
    var minY=1e9,maxY=-1e9,i;
    for(i=0;i<pts.length;i++){if(pts[i].y<minY)minY=pts[i].y;if(pts[i].y>maxY)maxY=pts[i].y;}
    var mask=new Uint8Array(cw*ch),any=false,x0=cw,y0=ch,x1=-1,y1=-1;
    for(var y=Math.max(0,Math.floor(minY));y<=Math.min(ch-1,Math.ceil(maxY));y++){
      var yc=y+0.5,xs=[];
      for(i=0;i<pts.length;i++){
        var a=pts[i],b=pts[(i+1)%pts.length];
        if((a.y<=yc&&b.y>yc)||(b.y<=yc&&a.y>yc))xs.push(a.x+(yc-a.y)/(b.y-a.y)*(b.x-a.x));
      }
      xs.sort(function(u,v){return u-v;});
      for(var k=0;k+1<xs.length;k+=2){
        var xa=Math.max(0,Math.round(xs[k])),xb=Math.min(cw-1,Math.round(xs[k+1]));
        for(var x=xa;x<=xb;x++){mask[y*cw+x]=1;any=true;if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y;}
      }
    }
    return any?{mask:mask,x0:x0,y0:y0,x1:x1,y1:y1}:null;
  }
  function snapRegion(d,cw,ch,pts){
    // Rough-trace segmentation: deep inside the trace = foreground seeds, well
    // outside = background seeds; band pixels join whichever side is nearer in
    // GEODESIC distance (stepping across a strong color/alpha edge is costly),
    // so the cut snaps to the nearest real boundary around the traced area.
    var pf=fillPolygon(pts,cw,ch);if(!pf)return null;
    var band=12,PAD=band+4;
    var bx0=Math.max(0,pf.x0-PAD),by0=Math.max(0,pf.y0-PAD),bx1=Math.min(cw-1,pf.x1+PAD),by1=Math.min(ch-1,pf.y1+PAD);
    var bw=bx1-bx0+1,bh=by1-by0+1,n=bw*bh,i,x,y,p;
    var R=new Uint8Array(n);
    for(y=0;y<bh;y++)for(x=0;x<bw;x++)R[y*bw+x]=pf.mask[(y+by0)*cw+(x+bx0)];
    function chamfer(zeroIsSource){
      // City-block distance to the nearest source cell (two-pass).
      var INF=1e9,dist=new Int32Array(n);
      for(i=0;i<n;i++)dist[i]=(R[i]===zeroIsSource?0:INF);
      for(y=0;y<bh;y++)for(x=0;x<bw;x++){p=y*bw+x;if(x>0&&dist[p-1]+1<dist[p])dist[p]=dist[p-1]+1;if(y>0&&dist[p-bw]+1<dist[p])dist[p]=dist[p-bw]+1;}
      for(y=bh-1;y>=0;y--)for(x=bw-1;x>=0;x--){p=y*bw+x;if(x<bw-1&&dist[p+1]+1<dist[p])dist[p]=dist[p+1]+1;if(y<bh-1&&dist[p+bw]+1<dist[p])dist[p]=dist[p+bw]+1;}
      return dist;
    }
    var inDist=chamfer(0);   // distance from outside → deep-inside cells are large
    var outDist=chamfer(1);  // distance from inside → far-outside cells are large
    var hasCore=false;
    while(band>2){hasCore=false;for(i=0;i<n;i++)if(R[i]&&inDist[i]>=band){hasCore=true;break;}if(hasCore)break;band=band>>1;}
    if(!hasCore)return null; // trace too thin to define an inside
    function gcost(pa,pb){
      var ia=((pa/bw|0)+by0)*cw*4+((pa%bw)+bx0)*4,ib=((pb/bw|0)+by0)*cw*4+((pb%bw)+bx0)*4;
      return 1+Math.abs(d[ib]-d[ia])+Math.abs(d[ib+1]-d[ia+1])+Math.abs(d[ib+2]-d[ia+2])+Math.abs(d[ib+3]-d[ia+3]);
    }
    var INF=1e30,dI=new Float64Array(n),dO=new Float64Array(n);
    for(i=0;i<n;i++){
      var inside=R[i]&&inDist[i]>=band;
      var outside=(!R[i]&&outDist[i]>=band)||(i%bw===0)||(i%bw===bw-1)||(i<bw)||(i>=n-bw);
      dI[i]=inside?0:INF;dO[i]=(outside&&!inside)?0:INF;
    }
    function relaxScans(dist){
      for(var it=0;it<3;it++){
        for(y=0;y<bh;y++)for(x=0;x<bw;x++){p=y*bw+x;
          if(x>0){var c=dist[p-1]+gcost(p-1,p);if(c<dist[p])dist[p]=c;}
          if(y>0){var c2=dist[p-bw]+gcost(p-bw,p);if(c2<dist[p])dist[p]=c2;}}
        for(y=bh-1;y>=0;y--)for(x=bw-1;x>=0;x--){p=y*bw+x;
          if(x<bw-1){var c3=dist[p+1]+gcost(p+1,p);if(c3<dist[p])dist[p]=c3;}
          if(y<bh-1){var c4=dist[p+bw]+gcost(p+bw,p);if(c4<dist[p])dist[p]=c4;}}
      }
    }
    relaxScans(dI);relaxScans(dO);
    var out=new Uint8Array(cw*ch);
    for(y=0;y<bh;y++)for(x=0;x<bw;x++){
      p=y*bw+x;
      if(dI[p]>dO[p])continue;
      var gp=(y+by0)*cw+(x+bx0);
      if(d[gp*4+3]<8)continue; // never select transparent pixels
      out[gp]=1;
    }
    return out;
  }
  function traceSelect(pts,erase){
    var l=active();if(!l)return msg('選択できるレイヤがありません。画像を開いてください。',true);
    var cw=l.c.width,ch=l.c.height;
    var local=pts.map(function(p){return {x:p.x-(l.x||0),y:p.y-(l.y||0)};});
    if(erase&&(!sel||selLayerId!==l.id))return msg('解除できる選択がありません。',true);
    ensureSelFor(l);
    var d=l.c.getContext('2d').getImageData(0,0,cw,ch).data;
    var mask=snapRegion(d,cw,ch,local);
    if(!mask)return msg('トレース領域からオブジェクトを特定できませんでした。もう少し広く囲んでください。',true);
    var v=erase?0:1;
    for(var i=0;i<mask.length;i++)if(mask[i])sel[i]=v;
    afterSelChange('トレース領域を近くの境界にスナップしました。クリック/ドラッグで追加できます。');
  }
  function finishSelectGesture(pts,alt){
    var far=0;
    for(var i=1;i<pts.length;i++){var dx=pts[i].x-pts[0].x,dy=pts[i].y-pts[0].y,q=dx*dx+dy*dy;if(q>far)far=q;}
    if(pts.length<6||far<36)selectObjectAt(pts[0],0,alt); // a click (barely moved) = magic wand
    else traceSelect(pts,alt);
  }
  function expandSelection(px){
    var l=byId(selLayerId);
    if(!sel||!l)return msg('先に「選択」ツールでオブジェクトを選択してください。',true);
    var cw=l.c.width,ch=l.c.height,steps=Math.max(1,Math.min(8,Math.round(+px||2))),x,y,p;
    for(var r=0;r<steps;r++){
      var nx=new Uint8Array(sel);
      for(y=0;y<ch;y++)for(x=0;x<cw;x++){
        p=y*cw+x;
        if(sel[p])continue;
        if((x>0&&sel[p-1])||(x<cw-1&&sel[p+1])||(y>0&&sel[p-cw])||(y<ch-1&&sel[p+cw]))nx[p]=1;
      }
      sel=nx;
    }
    // Fill enclosed holes: anything not reachable from the layer border through
    // unselected pixels is inside the selection.
    var seen=new Uint8Array(cw*ch),stack=[];
    for(x=0;x<cw;x++){if(!sel[x]){seen[x]=1;stack.push(x);}var b=(ch-1)*cw+x;if(!sel[b]&&!seen[b]){seen[b]=1;stack.push(b);}}
    for(y=0;y<ch;y++){p=y*cw;if(!sel[p]&&!seen[p]){seen[p]=1;stack.push(p);}var e2=y*cw+cw-1;if(!sel[e2]&&!seen[e2]){seen[e2]=1;stack.push(e2);}}
    while(stack.length){
      p=stack.pop();x=p%cw;y=(p-x)/cw;
      var nbs=[x-1,y,x+1,y,x,y-1,x,y+1];
      for(var k=0;k<8;k+=2){
        var nx2=nbs[k],ny2=nbs[k+1];
        if(nx2<0||ny2<0||nx2>=cw||ny2>=ch)continue;
        var np=ny2*cw+nx2;
        if(!sel[np]&&!seen[np]){seen[np]=1;stack.push(np);}
      }
    }
    for(p=0;p<cw*ch;p++)if(!sel[p]&&!seen[p])sel[p]=1;
    afterSelChange('選択を'+steps+'px広げ、囲まれた穴を埋めました。');
  }
  function deleteOutsideSelection(){
    var l=byId(selLayerId);
    if(!sel||!l)return msg('先に「選択」ツールで残したいオブジェクトをクリックしてください。',true);
    pushHistory(snapPix(l));
    var x=l.c.getContext('2d'),im=x.getImageData(0,0,l.c.width,l.c.height),d=im.data;
    for(var i=0,n=l.c.width*l.c.height;i<n;i++){if(!sel[i])d[i*4+3]=0;}
    x.putImageData(im,0,0);
    clearSelection();
    msg('選択したオブジェクト以外を透明化しました。');
    render();renderLayers();saveSoon();
  }

  // --- Direct canvas interaction (move / brush / eraser / select) --------------
  function point(e){var r=view.getBoundingClientRect();return {x:(e.clientX-r.left)*(w/r.width),y:(e.clientY-r.top)*(h/r.height)};}
  function brushCtx(l,erase){
    var x=l.c.getContext('2d'),size=+$('brushSize').value||20;
    x.save();x.lineCap='round';x.lineJoin='round';x.lineWidth=size;
    if(erase){x.globalCompositeOperation='destination-out';x.strokeStyle='rgba(0,0,0,1)';x.fillStyle='rgba(0,0,0,1)';}
    else{x.globalCompositeOperation='source-over';x.strokeStyle=$('brushColor').value||'#111827';x.fillStyle=$('brushColor').value||'#111827';}
    return {x:x,size:size};
  }
  function paintDot(p,erase){var l=active();if(!l)return;var b=brushCtx(l,erase);b.x.beginPath();b.x.arc(p.x-(l.x||0),p.y-(l.y||0),b.size/2,0,Math.PI*2);b.x.fill();b.x.restore();requestRender();}
  function paintLine(a,b2,erase){var l=active();if(!l)return;var b=brushCtx(l,erase);b.x.beginPath();b.x.moveTo(a.x-(l.x||0),a.y-(l.y||0));b.x.lineTo(b2.x-(l.x||0),b2.y-(l.y||0));b.x.stroke();b.x.restore();requestRender();}
  function pointerDown(e){
    if(tool==='select'){
      e.preventDefault();
      try{view.setPointerCapture(e.pointerId);}catch(_){}
      tracing=true;traceAlt=!!e.altKey;tracePts=[point(e)];
      return;
    }
    if(!layers.length&&tool!=='move')addBlank('描画レイヤ');
    var l=active();if(!l)return;
    e.preventDefault();
    try{view.setPointerCapture(e.pointerId);}catch(_){}
    drawing=true;lastPt=point(e);dragStart={p:lastPt,x:(l.x||0),y:(l.y||0)};
    if(tool==='move')pushHistory(snapMeta());
    else{pushHistory(snapPix(l));paintDot(lastPt,tool==='eraser');}
  }
  function pointerMove(e){
    if(tracing){
      e.preventDefault();
      var tp=point(e),lp=tracePts[tracePts.length-1],dx=tp.x-lp.x,dy=tp.y-lp.y;
      if(dx*dx+dy*dy>=4){tracePts.push(tp);requestRender();}
      return;
    }
    if(!drawing)return;e.preventDefault();
    var p=point(e),l=active();if(!l)return;
    if(tool==='move'){l.x=dragStart.x+(p.x-dragStart.p.x);l.y=dragStart.y+(p.y-dragStart.p.y);requestRender();}
    else{paintLine(lastPt,p,tool==='eraser');lastPt=p;}
  }
  function pointerUp(){
    if(tracing){
      tracing=false;
      var pts=tracePts,alt=traceAlt;tracePts=[];traceAlt=false;
      finishSelectGesture(pts,alt);
      return;
    }
    if(!drawing)return;drawing=false;lastPt=null;dragStart=null;render();renderLayers();saveSoon();
  }

  function download(){var a=document.createElement('a'),ts=new Date().toISOString().replace(/[:.]/g,'-');render();a.href=view.toDataURL('image/png');a.download='agentforge-retouch-'+ts+'.png';document.body.appendChild(a);a.click();a.remove();}

  // --- Persistence: meta is cheap (AF.save); pixels encode only on real saves --
  function saveMeta(){try{AF.save({activeId:activeId,width:w,height:h,tool:tool,zoom:zoom,layers:layers.map(function(l){return {id:l.id,name:l.name,visible:l.visible,opacity:l.opacity,x:l.x||0,y:l.y||0};})});}catch(_){}}
  function saveMetaSoon(){clearTimeout(metaT);metaT=setTimeout(saveMeta,400);}
  function saveSoon(){clearTimeout(saveT);saveT=setTimeout(saveProject,700);}
  function saveProject(){
    if(drawing){saveSoon();return;}
    saveMeta();
    try{AF.saveBlob('retouch-project',JSON.stringify({w:w,h:h,activeId:activeId,tool:tool,zoom:zoom,layers:layers.map(function(l){return {id:l.id,name:l.name,visible:l.visible,opacity:l.opacity,x:l.x||0,y:l.y||0,data:l.c.toDataURL('image/png')};})}));}catch(_){}
  }
  function decodeLayer(rec){
    return new Promise(function(res){
      var im=new Image();
      im.onload=function(){var c=makeCanvas(im.naturalWidth||w,im.naturalHeight||h);c.getContext('2d').drawImage(im,0,0);res({id:rec.id||id(),name:rec.name||('レイヤ '+seq),visible:rec.visible!==false,opacity:+rec.opacity||1,x:+rec.x||0,y:+rec.y||0,c:c});};
      im.onerror=function(){msg('レイヤ画像のBlobがこの端末にありません。画像を開き直すか、保存済みプロジェクトを再読み込みしてください。',true);res({id:rec.id||id(),name:rec.name||('レイヤ '+seq),visible:rec.visible!==false,opacity:+rec.opacity||1,x:+rec.x||0,y:+rec.y||0,c:makeCanvas()});};
      im.src=rec.data||'';
    });
  }
  function loadProject(){
    Promise.resolve(AF.loadBlob('retouch-project')).then(function(raw){
      if(!raw)return Promise.resolve(AF.load()).then(function(s){
        if(s){w=s.width||w;h=s.height||h;activeId=s.activeId||null;tool=s.tool||tool;zoom=+s.zoom||zoom;setTool(tool);
          if(Array.isArray(s.layers)&&s.layers.length)msg('保存済みプロジェクトの画像本体がこの端末にありません。画像を開き直すと編集を再開できます。',true);}
        render();renderLayers();
      });
      var p;
      try{p=JSON.parse(String(raw));}catch(e){msg('保存済みプロジェクトを読めませんでした。',true);render();renderLayers();return;}
      w=p.w||w;h=p.h||h;tool=p.tool||tool;zoom=+p.zoom||zoom;setTool(tool);
      var recs=Array.isArray(p.layers)?p.layers:[],out=[],q=Promise.resolve();
      recs.forEach(function(rec){q=q.then(function(){return decodeLayer(rec).then(function(l){out.push(l);});});});
      q.then(function(){
        layers=out;activeId=p.activeId||((layers[0]||{}).id||null);syncControls();
        msg(layers.length?'保存済みプロジェクトを復元しました。':'画像を開くと編集できます。');
        if(!p.zoom&&layers.length)fitZoom();
        render();renderLayers();
      });
    });
  }

  // --- Wiring -------------------------------------------------------------------
  $('file').onchange=function(e){var f=e.target.files&&e.target.files[0];loadImageFile(f);e.target.value='';};
  ws.addEventListener('dragover',function(e){e.preventDefault();});
  ws.addEventListener('drop',function(e){e.preventDefault();var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];loadImageFile(f);});
  document.addEventListener('paste',function(e){
    var items=(e.clipboardData||{}).items||[];
    for(var i=0;i<items.length;i++){
      if(items[i].type&&items[i].type.indexOf('image/')===0){var f=items[i].getAsFile();if(f){loadImageFile(f);e.preventDefault();return;}}
    }
  });
  $('blank').onclick=function(){addBlank();};$('dup').onclick=duplicate;$('del').onclick=function(){removeLayer();};
  $('up').onclick=function(){move(1);};$('down').onclick=function(){move(-1);};
  $('undo').onclick=undo;$('redo').onclick=redo;$('clearLayer').onclick=clearLayer;$('crop').onclick=cropToContent;$('download').onclick=download;
  $('zoomIn').onclick=function(){zoomBy(1.25);};$('zoomOut').onclick=function(){zoomBy(1/1.25);};
  $('zoomFit').onclick=fitZoom;$('zoom100').onclick=function(){setZoom(1);};
  ws.addEventListener('wheel',function(e){if(!e.ctrlKey)return;e.preventDefault();zoomBy(e.deltaY<0?1.15:1/1.15);},{passive:false});
  $('toolMove').onclick=function(){setTool('move');};$('toolBrush').onclick=function(){setTool('brush');};$('toolEraser').onclick=function(){setTool('eraser');};$('toolSelect').onclick=function(){setTool('select');};
  $('delOutside').onclick=deleteOutsideSelection;
  $('expandSel').onclick=function(){expandSelection(2);};
  $('clearSel').onclick=function(){if(!sel)return msg('選択はありません。',true);clearSelection();render();msg('選択を解除しました。');};
  $('opacity').oninput=function(e){var l=active();if(l){l.opacity=(+e.target.value||0)/100;render();saveSoon();}};
  $('removeBg').onclick=function(){removeBackground(+$('threshold').value||42);};
  $('outline').onclick=function(){extractOutline(+$('threshold').value||42);};
  $('transparent').onclick=function(){transparentColor($('keycolor').value,+$('threshold').value||42);};
  $('adjust').onclick=function(){adjustActive(+$('brightness').value||0,+$('contrast').value||0);};
  view.addEventListener('pointerdown',pointerDown);view.addEventListener('pointermove',pointerMove);
  view.addEventListener('pointerup',pointerUp);window.addEventListener('pointerup',pointerUp);
  document.addEventListener('keydown',function(e){
    var tg=(e.target&&e.target.tagName||'').toLowerCase();
    if(tg==='input'||tg==='textarea'||tg==='select')return;
    var k=String(e.key||'').toLowerCase();
    if((e.ctrlKey||e.metaKey)&&k==='z'){e.preventDefault();if(e.shiftKey)redo();else undo();}
    else if((e.ctrlKey||e.metaKey)&&k==='y'){e.preventDefault();redo();}
    else if(k==='escape'&&sel){clearSelection();render();msg('選択を解除しました。');}
    else if(!e.ctrlKey&&!e.metaKey&&!e.altKey){
      if(k==='v')setTool('move');else if(k==='b')setTool('brush');else if(k==='e')setTool('eraser');else if(k==='w')setTool('select');
    }
  });
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_blank_layer')addBlank(args.name);
    else if(name==='select_layer')selectLayer(args);
    else if(name==='rename_layer')renameLayer(args);
    else if(name==='duplicate_layer')duplicate();
    else if(name==='delete_layer')removeLayer(args);
    else if(name==='undo')undo();
    else if(name==='redo')redo();
    else if(name==='clear_layer')clearLayer();
    else if(name==='crop_to_content')cropToContent();
    else if(name==='set_tool')setTool(args.tool||'move');
    else if(name==='set_zoom'){if(args.fit)fitZoom();else setZoom((+args.percent||100)/100);}
    else if(name==='select_object_at')selectObjectAt({x:+args.x||0,y:+args.y||0},+args.threshold||0);
    else if(name==='expand_selection')expandSelection(+args.pixels||2);
    else if(name==='clear_selection'){clearSelection();render();msg('選択を解除しました。');}
    else if(name==='delete_outside_selection')deleteOutsideSelection();
    else if(name==='set_layer_opacity'){var l=active();if(l){l.opacity=Math.max(0,Math.min(1,+args.opacity));render();renderLayers();saveSoon();}}
    else if(name==='toggle_layer_visibility'){var l=active();if(l){l.visible=args.visible!==false;render();renderLayers();saveSoon();}}
    else if(name==='move_layer'){if(args.dx!==undefined||args.dy!==undefined)moveActiveLayer(args.dx,args.dy);else move(args.direction==='down'?-1:1);}
    else if(name==='remove_background')removeBackground(+args.threshold||42);
    else if(name==='extract_outline')extractOutline(+args.threshold||42);
    else if(name==='make_color_transparent')transparentColor(args.color||'#ffffff',+args.threshold||42);
    else if(name==='adjust_color')adjustActive(+args.brightness||0,+args.contrast||0);
  };
  render();renderLayers();loadProject();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "retouch",
    "title": "レタッチスタジオ",
    "description": "画像を読み込み（ファイル選択・ドラッグ&ドロップ・貼り付け）、レイヤ管理（サムネイル付き）、移動、ブラシ、消しゴム、オブジェクト選択（クリックで境界検出・おおよそ囲むトレースで近くの境界にスナップ・クリック追加で選択拡大・連続部分は自動結合・Alt+クリックで部分解除・選択の膨張と穴埋め）と選択以外の背景透過、ズーム/フィット表示、Undo/Redo（Ctrl+Z/Y）、輪郭抽出、背景削除、色の透過処理、切り抜き、明るさ/コントラスト補正、PNG書き出しができる基本レタッチアプリ。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "add_blank_layer", "description": "空のレイヤを追加",
         "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}}},
        {"name": "select_layer", "description": "レイヤIDまたはレイヤ名で対象レイヤを選択",
         "inputSchema": {"type": "object", "properties": {"layer_id": {"type": "string"}, "layer_name": {"type": "string"}}}},
        {"name": "rename_layer", "description": "レイヤID/名前で対象を指定してレイヤ名を変更。指定が無い場合は現在のレイヤを変更",
         "inputSchema": {"type": "object", "properties": {"layer_id": {"type": "string"}, "layer_name": {"type": "string"}, "name": {"type": "string"}}, "required": ["name"]}},
        {"name": "duplicate_layer", "description": "現在のレイヤを複製",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "delete_layer", "description": "レイヤID/名前で対象を指定して削除。指定が無い場合は現在のレイヤを削除",
         "inputSchema": {"type": "object", "properties": {"layer_id": {"type": "string"}, "layer_name": {"type": "string"}}}},
        {"name": "undo", "description": "直前の破壊的操作や編集操作を取り消す",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "redo", "description": "Undoした操作をやり直す",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "clear_layer", "description": "現在のレイヤの画像を消去する",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "crop_to_content", "description": "表示中の不透明ピクセル範囲でキャンバス全体を切り抜く",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "set_tool", "description": "キャンバス直接操作ツールを選ぶ（select=クリックでオブジェクト選択）",
         "inputSchema": {"type": "object", "properties": {"tool": {"type": "string", "enum": ["move", "brush", "eraser", "select"]}}, "required": ["tool"]}},
        {"name": "set_zoom", "description": "表示ズームを％で設定する。fit=true で全体が見えるようにフィットする",
         "inputSchema": {"type": "object", "properties": {"percent": {"type": "number"}, "fit": {"type": "boolean"}}}},
        {"name": "select_object_at", "description": "キャンバス座標(x,y)のオブジェクトを境界検出して選択に追加する。既存の選択と連続していれば1つのオブジェクトとして結合される",
         "inputSchema": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "threshold": {"type": "number"}}, "required": ["x", "y"]}},
        {"name": "expand_selection", "description": "選択範囲を指定ピクセル（既定2）広げ、選択に囲まれた小さな穴を埋める",
         "inputSchema": {"type": "object", "properties": {"pixels": {"type": "number"}}}},
        {"name": "clear_selection", "description": "オブジェクト選択を解除する",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "delete_outside_selection", "description": "選択したオブジェクト以外を透明化する（選択ベースの背景透過）",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "set_layer_opacity", "description": "現在のレイヤの不透明度を0〜1で設定",
         "inputSchema": {"type": "object", "properties": {"opacity": {"type": "number"}}, "required": ["opacity"]}},
        {"name": "toggle_layer_visibility", "description": "現在のレイヤの表示/非表示を切替",
         "inputSchema": {"type": "object", "properties": {"visible": {"type": "boolean"}}, "required": ["visible"]}},
        {"name": "move_layer", "description": "現在のレイヤの重なり順を上下に動かす、またはキャンバス上の位置をdx/dyで移動",
         "inputSchema": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "dx": {"type": "number"}, "dy": {"type": "number"}}}},
        {"name": "remove_background", "description": "四隅の背景色に近いピクセルを透明化",
         "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number"}}}},
        {"name": "extract_outline", "description": "現在のレイヤから輪郭レイヤを生成",
         "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number"}}}},
        {"name": "make_color_transparent", "description": "指定色に近いピクセルを透明化",
         "inputSchema": {"type": "object", "properties": {"color": {"type": "string"}, "threshold": {"type": "number"}}, "required": ["color"]}},
        {"name": "adjust_color", "description": "現在のレイヤに明るさ/コントラスト補正を適用",
         "inputSchema": {"type": "object", "properties": {"brightness": {"type": "number"}, "contrast": {"type": "number"}}}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "activeId": {"type": "string"},
            "width": {"type": "number"},
            "height": {"type": "number"},
            "tool": {"type": "string", "enum": ["move", "brush", "eraser", "select"]},
            "zoom": {"type": "number", "description": "表示ズーム倍率（1=100%）。画像データには影響しない。"},
            "layers": {
                "type": "array",
                "description": "レイヤのメタ情報。画像本体はAF.saveBlob('retouch-project')に保存される。",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "visible": {"type": "boolean"},
                        "opacity": {"type": "number"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                    },
                    "required": ["id", "name", "visible", "opacity"],
                },
            },
        },
    },
    "worker_instructions": (
        "レタッチスタジオ操作用ワーカー。ユーザーが読み込んだ画像に対し、レイヤ追加、選択、リネーム、複製、削除、"
        "表示切替、不透明度変更、順序変更、キャンバス上の位置移動、ツール選択、ズーム/フィット表示、背景削除、"
        "輪郭抽出、指定色の透過処理、透明部分の切り抜き、明るさ/コントラスト補正、Undo/Redoを担当する。"
        "オブジェクト選択はクリック位置から境界検出して追加され、ドラッグでおおよそ囲むと近くの境界にスナップする。"
        "連続する部分は1つのオブジェクトに結合され、Alt+クリックで部分解除できる。"
        "選択が細かく取りこぼす場合は、しきい値を上げる・トレースで囲む・expand_selection で広げて穴を埋める、を案内する。"
        "『選択した以外を消して』『選択ベースで背景を透過して』は delete_outside_selection を使う。"
        "クリックやトレースの位置指定はユーザー操作が必要なので、選択を頼まれたら set_tool tool='select' に切り替えて"
        "残したいオブジェクトをクリックまたはおおよそ囲むよう案内する。"
        "画像ファイルの読み込み（ファイル選択・ドラッグ&ドロップ・貼り付け）とブラシ/消しゴムのストローク描画はユーザー操作が必要。"
        "削除、レイヤ消去、背景削除、透過処理、補正のように復元しにくい操作は、対象や意図が曖昧なら実行前に聞き返す。"
    ),
    "worker_examples": [
        {"user": "新しいレイヤを作って", "command": {"name": "add_blank_layer", "arguments": {"name": "新規レイヤ"}}, "reply": "空のレイヤを追加します。"},
        {"user": "背景レイヤを選んで", "command": {"name": "select_layer", "arguments": {"layer_name": "背景"}}, "reply": "背景レイヤを選択します。"},
        {"user": "今のレイヤ名を人物にして", "command": {"name": "rename_layer", "arguments": {"name": "人物"}}, "reply": "現在のレイヤ名を人物に変更します。"},
        {"user": "消しゴムにして", "command": {"name": "set_tool", "arguments": {"tool": "eraser"}}, "reply": "消しゴムツールに切り替えます。"},
        {"user": "残したいものを選択したい", "command": {"name": "set_tool", "arguments": {"tool": "select"}}, "reply": "選択ツールに切り替えました。オブジェクトをクリックするか、ドラッグでおおよそ囲むと近くの境界にスナップして選択できます。"},
        {"user": "選択が細かく切れてしまう", "command": {"name": "expand_selection", "arguments": {"pixels": 2}}, "reply": "選択を2px広げて穴を埋めます。しきい値を上げてからのクリックや、ドラッグで囲むトレース選択も有効です。"},
        {"user": "選択した以外を消して", "command": {"name": "delete_outside_selection", "arguments": {}}, "reply": "選択したオブジェクト以外を透明化します。"},
        {"user": "選択をやり直したい", "command": {"name": "clear_selection", "arguments": {}}, "reply": "選択を解除しました。もう一度クリックで選び直せます。"},
        {"user": "全体が見えるようにして", "command": {"name": "set_zoom", "arguments": {"fit": True}}, "reply": "画像全体が見えるようにフィット表示します。"},
        {"user": "200%に拡大して", "command": {"name": "set_zoom", "arguments": {"percent": 200}}, "reply": "表示を200%に拡大します。"},
        {"user": "このレイヤを右に20px移動して", "command": {"name": "move_layer", "arguments": {"dx": 20, "dy": 0}}, "reply": "現在のレイヤを右へ移動します。"},
        {"user": "今のレイヤを半透明にして", "command": {"name": "set_layer_opacity", "arguments": {"opacity": 0.5}}, "reply": "現在のレイヤを半透明にします。"},
        {"user": "背景を消して", "command": {"name": "remove_background", "arguments": {"threshold": 42}}, "reply": "背景色に近い部分を透明化します。"},
        {"user": "輪郭を抽出して", "command": {"name": "extract_outline", "arguments": {"threshold": 42}}, "reply": "輪郭レイヤを作成します。"},
        {"user": "白を透明にして", "command": {"name": "make_color_transparent", "arguments": {"color": "#ffffff", "threshold": 42}}, "reply": "白に近い部分を透明化します。"},
        {"user": "余白を切り抜いて", "command": {"name": "crop_to_content", "arguments": {}}, "reply": "透明な余白を除いて切り抜きます。"},
        {"user": "少し明るくして", "command": {"name": "adjust_color", "arguments": {"brightness": 18, "contrast": 0}}, "reply": "現在のレイヤを少し明るくします。"},
        {"user": "戻して", "command": {"name": "undo", "arguments": {}}, "reply": "直前の操作を取り消します。"},
        {"user": "このレイヤを消して", "command": {"name": "", "arguments": {}}, "reply": "現在選択中のレイヤを削除してよいですか？"},
    ],
    "worker_eval_cases": [
        {"input": "人物レイヤを選択して", "expected": "select_layer を layer_name='人物' で実行する。該当が無ければ確認する。"},
        {"input": "今のレイヤをロゴにリネーム", "expected": "rename_layer を name='ロゴ' で実行し、AF.save で状態が保存される。"},
        {"input": "消しゴムを選んで", "expected": "set_tool を tool='eraser' で実行する。"},
        {"input": "画像全体を表示して", "expected": "set_zoom を fit=true で実行してフィット表示にする。"},
        {"input": "この人物だけ残して背景を消したい", "expected": "set_tool tool='select' に切り替え、残したいオブジェクトをクリックまたはドラッグでおおよそ囲むよう案内する。選択済みなら delete_outside_selection を実行する。"},
        {"input": "選択が細切れになる", "expected": "しきい値を上げる・ドラッグで囲むトレース選択・expand_selection のいずれかを提案する。"},
        {"input": "選択した以外を削除して", "expected": "選択が無ければ選択を促し、あれば delete_outside_selection を実行する（破壊的なので Undo 可能である旨を添えてよい）。"},
        {"input": "人物レイヤを10px下へ移動", "expected": "対象レイヤを選択してから move_layer を dy=10 で実行する。"},
        {"input": "背景レイヤを削除", "expected": "delete_layer を layer_name='背景' で実行する前に、曖昧さや削除確認が必要なら短く確認する。"},
        {"input": "白を透明にして", "expected": "make_color_transparent を color='#ffffff' で実行する。"},
        {"input": "透明になった余白を切り抜いて", "expected": "crop_to_content を実行して表示中の不透明範囲にキャンバスを切り抜く。"},
        {"input": "少しコントラストを上げて", "expected": "adjust_color を contrast の正の値で実行する。破壊的補正なので Undo 可能であることを前提にする。"},
        {"input": "戻して", "expected": "undo を実行して直前の編集を取り消す。"},
        {"input": "輪郭だけのレイヤを作って", "expected": "extract_outline を実行して新規輪郭レイヤを作成する。"},
        {"input": "全部消して最初から", "expected": "対象範囲が大きく復元しにくいため、実行せず確認する。"},
    ],
    "clarification_policy": "削除、背景削除、透過処理で対象レイヤや色が曖昧な場合は、実行前に短く確認する。",
    "dangerous_action_policy": "レイヤ削除、背景削除、広範囲の透過処理は復元しにくいため、曖昧な場合は確認する。",
}
