"""Default mini-app template: レタッチスタジオ (retouch)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef1f6;--panel:#ffffff;--ink:#172033;--mut:#677089;--line:#d9deea;--ac:#2563eb;--soft:#f7f9fd}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--ink)}
.app{height:100%;display:grid;grid-template-columns:260px 1fr 260px;grid-template-rows:auto 1fr;gap:10px;padding:10px}
.top{grid-column:1/4;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button,.filebtn{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:7px;padding:8px 10px;font-weight:700;font-size:13px;cursor:pointer}
button.primary,.filebtn.primary{background:var(--ac);border-color:var(--ac);color:#fff}button:disabled{opacity:.45;cursor:not-allowed}
.filebtn input{display:none}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;min-height:0;overflow:hidden}
.left,.right{display:flex;flex-direction:column}.panel h2{font-size:14px;margin:0;padding:12px;border-bottom:1px solid var(--line)}
.hint{font-size:12px;color:var(--mut);line-height:1.5}.toolbox{padding:10px;display:grid;gap:8px}.toolbox label{display:grid;gap:5px;font-size:12px;color:var(--mut);font-weight:700}
input[type=range]{width:100%}.workspace{position:relative;overflow:auto;background:#dfe3ec;border-radius:8px;border:1px solid var(--line)}
.stagewrap{min-width:100%;min-height:100%;display:grid;place-items:center;padding:28px}
.stage{position:relative;box-shadow:0 10px 30px rgba(23,32,51,.18);background-image:linear-gradient(45deg,#ccd2df 25%,transparent 25%),linear-gradient(-45deg,#ccd2df 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ccd2df 75%),linear-gradient(-45deg,transparent 75%,#ccd2df 75%);background-size:22px 22px;background-position:0 0,0 11px,11px -11px,-11px 0}
canvas{display:block;max-width:none}.empty{padding:24px;max-width:520px;text-align:center;background:rgba(255,255,255,.86);border:1px dashed #aeb7c8;border-radius:8px}
.layers{list-style:none;margin:0;padding:8px;overflow:auto;flex:1}.layers li{display:grid;grid-template-columns:24px 1fr auto;gap:8px;align-items:center;padding:8px;border:1px solid var(--line);border-radius:8px;margin-bottom:7px;background:var(--soft);cursor:pointer}
.layers li.on{border-color:var(--ac);box-shadow:0 0 0 2px rgba(37,99,235,.12);background:#eef5ff}.lname{font-weight:800;font-size:13px}.lmeta{font-size:11px;color:var(--mut)}
.eye{width:18px;height:18px}.mini{font-size:12px;padding:5px 7px}.row{display:flex;gap:6px;flex-wrap:wrap}.sw{width:30px;height:30px;border-radius:6px;border:1px solid var(--line);padding:0}
.status{padding:9px 10px;border-top:1px solid var(--line);font-size:12px;color:var(--mut);min-height:36px}.danger{color:#b42318}
@media(max-width:880px){.app{grid-template-columns:1fr;grid-template-rows:auto auto minmax(360px,1fr) auto}.top,.left,.workspace,.right{grid-column:1}.left,.right{max-height:220px}}
</style></head><body>
<div class="app">
  <div class="top">
    <label class="filebtn primary">画像を開く<input id="file" type="file" accept="image/*"></label>
    <button id="blank">空レイヤ</button><button id="dup">複製</button><button id="del">削除</button>
    <button id="up">上へ</button><button id="down">下へ</button>
    <button id="download" class="primary">PNGダウンロード</button>
  </div>
  <section class="panel left">
    <h2>レイヤ</h2>
    <ul class="layers" id="layers"></ul>
    <div class="status" id="status">画像を開くと編集できます。</div>
  </section>
  <main class="workspace">
    <div class="stagewrap"><div class="stage" id="stage"><canvas id="view"></canvas><div class="empty" id="empty"><b>レタッチスタジオ</b><p class="hint">画像を読み込み、レイヤ管理、輪郭抽出、背景削除、色の透過処理を試せます。画像処理はブラウザ内で実行します。</p></div></div></div>
  </main>
  <section class="panel right">
    <h2>処理</h2>
    <div class="toolbox">
      <label>不透明度 <input type="range" id="opacity" min="0" max="100" value="100"></label>
      <label>しきい値 <input type="range" id="threshold" min="5" max="140" value="42"></label>
      <label>透過色 <input type="color" id="keycolor" value="#ffffff"></label>
      <div class="row">
        <button id="removeBg">背景削除</button>
        <button id="outline">輪郭抽出</button>
        <button id="transparent">透過処理</button>
      </div>
      <p class="hint">背景削除は四隅の色に近いピクセルを透明化します。透過処理は指定色に近いピクセルを透明化します。輪郭抽出は現在レイヤから新しい輪郭レイヤを作ります。</p>
    </div>
  </section>
</div>
<script>
(function(){
  var view=document.getElementById('view'),vctx=view.getContext('2d'),stage=document.getElementById('stage');
  var layers=[],activeId=null,w=900,h=560,seq=1,saveT=null;
  function id(){return 'layer_'+Date.now().toString(36)+'_'+(seq++);}
  function active(){return layers.find(function(l){return l.id===activeId;})||layers[layers.length-1]||null;}
  function msg(t,bad){var e=document.getElementById('status');e.textContent=t;e.className='status'+(bad?' danger':'');}
  function makeCanvas(){var c=document.createElement('canvas');c.width=w;c.height=h;return c;}
  function layerCanvas(layer){var c=makeCanvas(),x=c.getContext('2d'),im=new Image();return new Promise(function(res){im.onload=function(){x.clearRect(0,0,w,h);x.drawImage(im,0,0,w,h);res(c);};im.onerror=function(){res(c);};im.src=layer.data||'';});}
  function syncCanvasSize(){view.width=w;view.height=h;view.style.width=w+'px';view.style.height=h+'px';stage.style.width=w+'px';stage.style.height=h+'px';}
  function render(){
    syncCanvasSize();vctx.clearRect(0,0,w,h);
    var p=Promise.resolve();
    layers.forEach(function(l){p=p.then(function(){if(!l.visible)return;return layerCanvas(l).then(function(c){vctx.globalAlpha=l.opacity;vctx.drawImage(c,0,0);vctx.globalAlpha=1;});});});
    p.then(function(){document.getElementById('empty').style.display=layers.length?'none':'block';renderLayers();});
  }
  function renderLayers(){
    var ul=document.getElementById('layers');ul.innerHTML='';
    layers.slice().reverse().forEach(function(l){
      var li=document.createElement('li');li.className=l.id===activeId?'on':'';
      li.innerHTML='<input class="eye" type="checkbox"><div><div class="lname"></div><div class="lmeta"></div></div><button class="mini">選択</button>';
      li.querySelector('.eye').checked=l.visible;li.querySelector('.lname').textContent=l.name;li.querySelector('.lmeta').textContent=Math.round(l.opacity*100)+'%';
      li.onclick=function(){activeId=l.id;syncControls();renderLayers();};
      li.querySelector('.eye').onclick=function(e){e.stopPropagation();l.visible=e.target.checked;render();saveSoon();};
      li.querySelector('button').onclick=function(e){e.stopPropagation();activeId=l.id;syncControls();renderLayers();};
      ul.appendChild(li);
    });
  }
  function syncControls(){var l=active();document.getElementById('opacity').value=l?Math.round(l.opacity*100):100;}
  function canvasToLayer(c,name){return {id:id(),name:name||('レイヤ '+seq),visible:true,opacity:1,data:c.toDataURL('image/png')};}
  function addLayerFromImage(img,name){
    w=Math.max(320,Math.min(1800,img.naturalWidth||img.width||900));h=Math.max(240,Math.min(1200,img.naturalHeight||img.height||560));
    var c=makeCanvas(),x=c.getContext('2d');x.drawImage(img,0,0,w,h);
    var l=canvasToLayer(c,name||'画像 '+seq);layers.push(l);activeId=l.id;msg('画像を読み込みました。');render();saveSoon();
  }
  function addBlank(name){var c=makeCanvas(),l=canvasToLayer(c,name||'空レイヤ '+seq);layers.push(l);activeId=l.id;msg('空レイヤを追加しました。');render();saveSoon();}
  function duplicate(){var l=active();if(!l)return msg('複製するレイヤがありません。',true);var n=JSON.parse(JSON.stringify(l));n.id=id();n.name=l.name+' コピー';layers.push(n);activeId=n.id;render();saveSoon();}
  function removeLayer(){var l=active();if(!l)return msg('削除するレイヤがありません。',true);layers=layers.filter(function(x){return x.id!==l.id;});activeId=layers.length?layers[layers.length-1].id:null;render();saveSoon();}
  function move(dir){var l=active();if(!l)return;var i=layers.indexOf(l),j=i+dir;if(j<0||j>=layers.length)return;layers[i]=layers[j];layers[j]=l;render();saveSoon();}
  function parseHex(hex){var n=parseInt(String(hex).replace('#',''),16);return [(n>>16)&255,(n>>8)&255,n&255];}
  function dist(r,g,b,c){var dr=r-c[0],dg=g-c[1],db=b-c[2];return Math.sqrt(dr*dr+dg*dg+db*db);}
  function corners(data){var pts=[[0,0],[w-1,0],[0,h-1],[w-1,h-1]],r=0,g=0,b=0,n=0;pts.forEach(function(p){var i=(p[1]*w+p[0])*4;if(data[i+3]>0){r+=data[i];g+=data[i+1];b+=data[i+2];n++;}});return n?[r/n,g/n,b/n]:[255,255,255];}
  function mutateActive(fn,label){var l=active();if(!l)return msg('処理するレイヤがありません。',true);layerCanvas(l).then(function(c){var x=c.getContext('2d'),im=x.getImageData(0,0,w,h);fn(im.data);x.putImageData(im,0,0);l.data=c.toDataURL('image/png');msg(label);render();saveSoon();});}
  function removeBackground(th){mutateActive(function(d){var c=corners(d);for(var i=0;i<d.length;i+=4){if(d[i+3]&&dist(d[i],d[i+1],d[i+2],c)<th)d[i+3]=0;}},'背景に近い色を透明化しました。');}
  function transparentColor(hex,th){var c=parseHex(hex);mutateActive(function(d){for(var i=0;i<d.length;i+=4){if(d[i+3]&&dist(d[i],d[i+1],d[i+2],c)<th)d[i+3]=0;}},'指定色を透明化しました。');}
  function extractOutline(th){
    var l=active();if(!l)return msg('輪郭抽出するレイヤがありません。',true);
    layerCanvas(l).then(function(c){
      var src=c.getContext('2d').getImageData(0,0,w,h).data,out=makeCanvas(),ox=out.getContext('2d'),img=ox.createImageData(w,h),dst=img.data;
      function lum(p){return src[p+3]===0?0:(src[p]*.299+src[p+1]*.587+src[p+2]*.114)*(src[p+3]/255);}
      for(var y=1;y<h-1;y++)for(var x=1;x<w-1;x++){var p=(y*w+x)*4,a=src[p+3];if(a<8)continue;var gx=Math.abs(lum(p+4)-lum(p-4)),gy=Math.abs(lum(p+w*4)-lum(p-w*4));var edge=gx+gy>th||src[p-4+3]<12||src[p+4+3]<12||src[p-w*4+3]<12||src[p+w*4+3]<12;if(edge){dst[p]=20;dst[p+1]=24;dst[p+2]=32;dst[p+3]=230;}}
      ox.putImageData(img,0,0);var nl=canvasToLayer(out,'輪郭 '+seq);layers.push(nl);activeId=nl.id;msg('輪郭レイヤを作成しました。');render();saveSoon();
    });
  }
  function download(){var a=document.createElement('a'),ts=new Date().toISOString().replace(/[:.]/g,'-');a.href=view.toDataURL('image/png');a.download='agentforge-retouch-'+ts+'.png';document.body.appendChild(a);a.click();a.remove();}
  function saveSoon(){clearTimeout(saveT);saveT=setTimeout(save,350);}
  function save(){try{AF.save({activeId:activeId,width:w,height:h,layers:layers.map(function(l){return {id:l.id,name:l.name,visible:l.visible,opacity:l.opacity};})});AF.saveBlob('retouch-project',JSON.stringify({w:w,h:h,activeId:activeId,layers:layers}));}catch(_){}}
  function load(){Promise.resolve(AF.loadBlob('retouch-project')).then(function(raw){if(!raw)return Promise.resolve(AF.load()).then(function(s){if(s){w=s.width||w;h=s.height||h;activeId=s.activeId||null;}render();});try{var p=JSON.parse(String(raw));w=p.w||w;h=p.h||h;layers=Array.isArray(p.layers)?p.layers:[];activeId=p.activeId||((layers[0]||{}).id||null);msg(layers.length?'保存済みプロジェクトを復元しました。':'画像を開くと編集できます。');}catch(e){msg('保存済みプロジェクトを読めませんでした。',true);}render();});}
  document.getElementById('file').onchange=function(e){var f=e.target.files&&e.target.files[0];if(!f)return;var r=new FileReader();r.onload=function(){var im=new Image();im.onload=function(){addLayerFromImage(im,f.name||'画像');};im.src=String(r.result);};r.readAsDataURL(f);e.target.value='';};
  document.getElementById('blank').onclick=function(){addBlank();};document.getElementById('dup').onclick=duplicate;document.getElementById('del').onclick=removeLayer;document.getElementById('up').onclick=function(){move(1);};document.getElementById('down').onclick=function(){move(-1);};document.getElementById('download').onclick=download;
  document.getElementById('opacity').oninput=function(e){var l=active();if(l){l.opacity=(+e.target.value||0)/100;render();saveSoon();}};
  document.getElementById('removeBg').onclick=function(){removeBackground(+document.getElementById('threshold').value||42);};
  document.getElementById('outline').onclick=function(){extractOutline(+document.getElementById('threshold').value||42);};
  document.getElementById('transparent').onclick=function(){transparentColor(document.getElementById('keycolor').value,+document.getElementById('threshold').value||42);};
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_blank_layer')addBlank(args.name);
    else if(name==='duplicate_layer')duplicate();
    else if(name==='delete_layer')removeLayer();
    else if(name==='set_layer_opacity'){var l=active();if(l){l.opacity=Math.max(0,Math.min(1,+args.opacity));render();saveSoon();}}
    else if(name==='toggle_layer_visibility'){var l=active();if(l){l.visible=args.visible!==false;render();saveSoon();}}
    else if(name==='move_layer'){move(args.direction==='down'?-1:1);}
    else if(name==='remove_background')removeBackground(+args.threshold||42);
    else if(name==='extract_outline')extractOutline(+args.threshold||42);
    else if(name==='make_color_transparent')transparentColor(args.color||'#ffffff',+args.threshold||42);
  };
  syncCanvasSize();render();load();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "retouch",
    "title": "レタッチスタジオ",
    "description": "画像を読み込み、レイヤ管理、輪郭抽出、背景削除、色の透過処理、PNG書き出しができる基本レタッチアプリ。",
    "kind": "app",
    "theme": "default",
    "html": _HTML,
    "commands": [
        {"name": "add_blank_layer", "description": "空のレイヤを追加",
         "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}}},
        {"name": "duplicate_layer", "description": "現在のレイヤを複製",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "delete_layer", "description": "現在のレイヤを削除",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "set_layer_opacity", "description": "現在のレイヤの不透明度を0〜1で設定",
         "inputSchema": {"type": "object", "properties": {"opacity": {"type": "number"}}, "required": ["opacity"]}},
        {"name": "toggle_layer_visibility", "description": "現在のレイヤの表示/非表示を切替",
         "inputSchema": {"type": "object", "properties": {"visible": {"type": "boolean"}}, "required": ["visible"]}},
        {"name": "move_layer", "description": "現在のレイヤを上または下へ移動",
         "inputSchema": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}}, "required": ["direction"]}},
        {"name": "remove_background", "description": "四隅の背景色に近いピクセルを透明化",
         "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number"}}}},
        {"name": "extract_outline", "description": "現在のレイヤから輪郭レイヤを生成",
         "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number"}}}},
        {"name": "make_color_transparent", "description": "指定色に近いピクセルを透明化",
         "inputSchema": {"type": "object", "properties": {"color": {"type": "string"}, "threshold": {"type": "number"}}, "required": ["color"]}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "activeId": {"type": "string"},
            "width": {"type": "number"},
            "height": {"type": "number"},
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
                    },
                    "required": ["id", "name", "visible", "opacity"],
                },
            },
        },
    },
    "worker_instructions": (
        "レタッチスタジオ操作用ワーカー。ユーザーが読み込んだ画像に対し、レイヤ追加、複製、削除、"
        "表示切替、不透明度変更、順序変更、背景削除、輪郭抽出、指定色の透過処理を担当する。"
        "画像ファイルの読み込みやキャンバス上の直接編集はユーザー操作が必要。"
        "削除、背景削除、透過処理のように復元しにくい操作は、対象や意図が曖昧なら実行前に聞き返す。"
    ),
    "worker_examples": [
        {"user": "新しいレイヤを作って", "command": {"name": "add_blank_layer", "arguments": {"name": "新規レイヤ"}}, "reply": "空のレイヤを追加します。"},
        {"user": "今のレイヤを半透明にして", "command": {"name": "set_layer_opacity", "arguments": {"opacity": 0.5}}, "reply": "現在のレイヤを半透明にします。"},
        {"user": "背景を消して", "command": {"name": "remove_background", "arguments": {"threshold": 42}}, "reply": "背景色に近い部分を透明化します。"},
        {"user": "輪郭を抽出して", "command": {"name": "extract_outline", "arguments": {"threshold": 42}}, "reply": "輪郭レイヤを作成します。"},
        {"user": "白を透明にして", "command": {"name": "make_color_transparent", "arguments": {"color": "#ffffff", "threshold": 42}}, "reply": "白に近い部分を透明化します。"},
        {"user": "このレイヤを消して", "command": {"name": "", "arguments": {}}, "reply": "現在選択中のレイヤを削除してよいですか？"},
    ],
    "clarification_policy": "削除、背景削除、透過処理で対象レイヤや色が曖昧な場合は、実行前に短く確認する。",
    "dangerous_action_policy": "レイヤ削除、背景削除、広範囲の透過処理は復元しにくいため、曖昧な場合は確認する。",
}
