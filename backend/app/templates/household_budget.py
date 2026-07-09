"""Default mini-app template: 家計簿 (household_budget)."""

_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f7f2;--card:#fff;--ac:#287c5a;--fg:#24312b;--mut:#7c8b82;--bd:#e2e8de;--soft:#edf5ef;--red:#c95b5b;--blue:#3d6fb4}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);font-family:system-ui,sans-serif;color:var(--fg)}
.wrap{max-width:1080px;margin:0 auto;padding:16px;display:grid;gap:12px}
h1{font-size:20px;margin:0}.head{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.month{display:flex;align-items:center;gap:8px}.month button,.form button,.row button{border:0;border-radius:9px;padding:8px 11px;font-weight:700;cursor:pointer}
.month button{background:#fff;border:1px solid var(--bd);color:var(--ac)}.month strong{min-width:110px;text-align:center}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px}
.card .l{font-size:12px;color:var(--mut);font-weight:700}.card .v{font-size:24px;font-weight:850;margin-top:4px}.plus{color:var(--blue)}.minus{color:var(--red)}
.form{display:grid;grid-template-columns:130px 100px 120px 1fr 130px auto;gap:8px;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px}
input,select{min-width:0;padding:10px;border:1px solid var(--bd);border-radius:9px;font-size:14px;background:#fff;color:var(--fg)}
.form button{background:var(--ac);color:#fff}.grid{display:grid;grid-template-columns:1fr 300px;gap:12px}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:12px;overflow:hidden}.panel h2{font-size:14px;margin:0;padding:12px;background:var(--soft);color:var(--ac)}
.list{display:grid}.row{display:grid;grid-template-columns:92px 74px 110px 1fr 110px 40px;gap:8px;align-items:center;padding:10px 12px;border-top:1px solid var(--bd)}
.row:first-child{border-top:0}.row .type{font-weight:800;font-size:12px}.row .amt{text-align:right;font-weight:850}.row .memo{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.row button{background:#fff;color:var(--mut);padding:5px}
.empty{padding:22px;text-align:center;color:var(--mut)}.cats{display:grid;gap:8px;padding:12px}.bar{height:9px;background:#eef1ec;border-radius:999px;overflow:hidden}.bar span{display:block;height:100%;background:var(--ac)}.catline{display:grid;gap:4px}.catline div{display:flex;justify-content:space-between;font-size:13px}
@media(max-width:780px){.cards{grid-template-columns:1fr}.form{grid-template-columns:1fr 1fr}.form .wide{grid-column:1/-1}.grid{grid-template-columns:1fr}.row{grid-template-columns:78px 62px 1fr 88px 34px}.row .cat{display:none}}
</style></head><body>
<div class="wrap">
  <div class="head"><h1>家計簿</h1><div class="month"><button id="prev">前月</button><strong id="month"></strong><button id="next">翌月</button></div></div>
  <div class="cards">
    <div class="card"><div class="l">収入</div><div class="v plus" id="income">0円</div></div>
    <div class="card"><div class="l">支出</div><div class="v minus" id="expense">0円</div></div>
    <div class="card"><div class="l">差引</div><div class="v" id="balance">0円</div></div>
  </div>
  <div class="form">
    <input id="date" type="date">
    <select id="type"><option value="expense">支出</option><option value="income">収入</option></select>
    <select id="category"><option>食費</option><option>日用品</option><option>交通</option><option>交際</option><option>趣味</option><option>住居</option><option>給与</option><option>その他</option></select>
    <input id="memo" class="wide" placeholder="内容（例：ランチ、電車、給料）">
    <input id="amount" type="number" inputmode="numeric" placeholder="金額">
    <button id="add">追加</button>
  </div>
  <div class="grid">
    <section class="panel"><h2>明細</h2><div id="list" class="list"></div></section>
    <section class="panel"><h2>カテゴリ別支出</h2><div id="cats" class="cats"></div></section>
  </div>
</div>
<script>
(function(){
  var tx=[],shown=new Date(),editing=null;
  var $=function(id){return document.getElementById(id);};
  function ym(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');}
  function iso(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
  function yen(n){return Math.round(Number(n)||0).toLocaleString('ja-JP')+'円';}
  function uid(){return 'b'+Date.now().toString(36)+Math.floor(Math.random()*1e4).toString(36);}
  function save(){AF.save({transactions:tx});}
  function monthItems(){var m=ym(shown);return tx.filter(function(x){return String(x.date||'').slice(0,7)===m;}).sort(function(a,b){return String(b.date).localeCompare(String(a.date));});}
  function render(){
    $('month').textContent=shown.getFullYear()+'年 '+(shown.getMonth()+1)+'月';
    var items=monthItems(), inc=0, exp=0, by={};
    items.forEach(function(x){var a=Number(x.amount)||0;if(x.type==='income')inc+=a;else{exp+=a;by[x.category||'その他']=(by[x.category||'その他']||0)+a;}});
    $('income').textContent=yen(inc);$('expense').textContent=yen(exp);$('balance').textContent=yen(inc-exp);$('balance').className='v '+(inc-exp<0?'minus':'plus');
    var list=$('list');list.innerHTML='';
    if(!items.length){list.innerHTML='<div class="empty">この月の明細はありません</div>';}else items.forEach(function(x){
      var r=document.createElement('div');r.className='row';
      r.innerHTML='<span></span><span class="type"></span><span class="cat"></span><span class="memo"></span><span class="amt"></span><button title="削除">×</button>';
      r.children[0].textContent=x.date||'';r.children[1].textContent=x.type==='income'?'収入':'支出';r.children[1].className='type '+(x.type==='income'?'plus':'minus');
      r.children[2].textContent=x.category||'その他';r.children[3].textContent=x.memo||'';r.children[4].textContent=yen(x.amount);r.children[4].className='amt '+(x.type==='income'?'plus':'minus');
      r.onclick=function(e){if(e.target.tagName==='BUTTON')return;openEdit(x);};
      r.children[5].onclick=function(){tx=tx.filter(function(y){return y.id!==x.id;});save();render();};
      list.appendChild(r);
    });
    var cats=$('cats');cats.innerHTML='';var max=Math.max(1,...Object.values(by));
    Object.keys(by).sort(function(a,b){return by[b]-by[a];}).forEach(function(k){
      var d=document.createElement('div');d.className='catline';d.innerHTML='<div><b></b><span></span></div><div class="bar"><span></span></div>';
      d.querySelector('b').textContent=k;d.querySelector('span').textContent=yen(by[k]);d.querySelector('.bar span').style.width=(by[k]/max*100)+'%';cats.appendChild(d);
    });
    if(!cats.innerHTML)cats.innerHTML='<div class="empty">支出カテゴリはありません</div>';
  }
  function clearForm(){editing=null;$('type').value='expense';$('category').value='食費';$('memo').value='';$('amount').value='';$('add').textContent='追加';}
  function openEdit(x){editing=x.id;$('date').value=x.date||iso(new Date());$('type').value=x.type||'expense';$('category').value=x.category||'その他';$('memo').value=x.memo||'';$('amount').value=x.amount||'';$('add').textContent='更新';}
  function upsert(data){
    var amount=Number(data.amount);if(!data.date||!amount)return;
    if(data.id){var e=tx.find(function(x){return x.id===data.id;});if(e){Object.assign(e,data);save();render();return;}}
    tx.push({id:uid(),date:data.date,type:data.type||'expense',category:data.category||'その他',memo:data.memo||'',amount:amount});save();render();
  }
  $('add').onclick=function(){
    upsert({id:editing,date:$('date').value,type:$('type').value,category:$('category').value,memo:$('memo').value,amount:Number($('amount').value)});
    clearForm();
  };
  $('prev').onclick=function(){shown.setMonth(shown.getMonth()-1);render();};
  $('next').onclick=function(){shown.setMonth(shown.getMonth()+1);render();};
  window.applyAgentCommand=function(name,args){args=args||{};
    if(name==='add_transaction'){
      if(Array.isArray(args.items)){args.items.forEach(function(it){it=it||{};upsert({date:it.date,type:it.type||'expense',category:it.category||'その他',memo:it.memo||'',amount:it.amount});});}
      else{upsert({date:args.date,type:args.type||'expense',category:args.category||'その他',memo:args.memo||'',amount:args.amount});}
    }
    else if(name==='delete_transaction'){tx=tx.filter(function(x){if(args.id)return x.id!==args.id;if(args.date&&x.date!==args.date)return true;if(args.category&&x.category!==args.category)return true;if(args.memo&&String(x.memo||'').indexOf(args.memo)<0)return true;return false;});save();render();}
    else if(name==='update_transaction'){tx.forEach(function(x){if((args.id&&x.id===args.id)||(!args.id&&(!args.date||x.date===args.date)&&(!args.memo||String(x.memo||'').indexOf(args.memo)>=0))){if(args.new_date)x.date=args.new_date;if(args.type)x.type=args.type;if(args.category)x.category=args.category;if(args.new_memo!==undefined)x.memo=args.new_memo;if(args.amount!==undefined)x.amount=Number(args.amount);}});save();render();}
    else if(name==='clear_month'){var m=args.month||ym(shown);tx=tx.filter(function(x){return String(x.date||'').slice(0,7)!==m;});save();render();}
  };
  (async function(){var s=await AF.load();if(s&&Array.isArray(s.transactions))tx=s.transactions;var n=new Date();$('date').value=iso(n);shown=new Date(n.getFullYear(),n.getMonth(),1);render();})();
})();
</script></body></html>"""

MANIFEST = {
    "feature": "household_budget",
    "title": "家計簿",
    "description": "支出・収入を日付、カテゴリ、メモ付きで記録し、月次の収支とカテゴリ別支出を確認できます。",
    "kind": "app",
    "theme": "forest",
    "html": _HTML,
    "commands": [
        {"name": "add_transaction", "description": "支出または収入を追加。複数明細は items に配列で渡せる",
         "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}, "type": {"type": "string", "description": "expense または income"}, "category": {"type": "string"}, "memo": {"type": "string"}, "amount": {"type": "number"}, "items": {"type": "array", "items": {"type": "object", "properties": {"date": {"type": "string"}, "type": {"type": "string"}, "category": {"type": "string"}, "memo": {"type": "string"}, "amount": {"type": "number"}}, "required": ["date", "amount"]}}}, "required": []}},
        {"name": "delete_transaction", "description": "日付・カテゴリ・メモ・idで明細を削除。複数一致なら複数削除",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "date": {"type": "string"}, "category": {"type": "string"}, "memo": {"type": "string"}}}},
        {"name": "update_transaction", "description": "明細を更新",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "date": {"type": "string"}, "memo": {"type": "string"}, "new_date": {"type": "string"}, "type": {"type": "string"}, "category": {"type": "string"}, "new_memo": {"type": "string"}, "amount": {"type": "number"}}}},
        {"name": "clear_month", "description": "指定月の明細を一括削除（month=YYYY-MM）",
         "inputSchema": {"type": "object", "properties": {"month": {"type": "string"}}}},
    ],
    "worker_state_mode": "hybrid",
    "state_schema": {
        "type": "object",
        "properties": {
            "transactions": {
                "type": "array",
                "description": "家計簿の明細一覧",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "type": {"type": "string", "description": "expense または income"},
                        "category": {"type": "string"},
                        "memo": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["id", "date", "type", "amount"],
                },
            }
        },
        "required": ["transactions"],
    },
    "worker_instructions": (
        "家計簿操作用ワーカー。支出・収入の追加、修正、削除、月次集計への質問に対応する。"
        "『ランチ800円』『昨日コンビニ450円』のような自然文は支出として transactions に追加する。"
        "『給料25万円』などは収入として追加する。日付がなければ今日、年がなければ今年を使う。"
        "カテゴリは食費、日用品、交通、交際、趣味、住居、給与、その他から自然に推定する。"
        "『ランチ800円と電車代320円を入れて』のような複数明細を1文で頼まれた場合は、"
        "それぞれ別 transaction として分解して処理する。追加と修正/削除が混ざる場合は、対象が一意な操作だけ実行し、曖昧なものは確認する。"
        "削除や修正で対象が曖昧な場合は、日付・金額・メモなどを聞き返す。"
        "月次合計やカテゴリ別合計を聞かれたら state を見て回答し、データ変更はしない。"
    ),
    "worker_examples": [
        {"user": "今日ランチ800円", "command": {"name": "add_transaction", "arguments": {"date": "YYYY-MM-DD", "type": "expense", "category": "食費", "memo": "ランチ", "amount": 800}}, "reply": "食費として追加します。"},
        {"user": "昨日、電車代320円を交通費で入れて", "command": {"name": "add_transaction", "arguments": {"date": "YYYY-MM-DD", "type": "expense", "category": "交通", "memo": "電車代", "amount": 320}}, "reply": "交通費として追加します。"},
        {"user": "今日ランチ800円と電車代320円を入れて", "command": {"name": "add_transaction", "arguments": {"items": [{"date": "YYYY-MM-DD", "type": "expense", "category": "食費", "memo": "ランチ", "amount": 800}, {"date": "YYYY-MM-DD", "type": "expense", "category": "交通", "memo": "電車代", "amount": 320}]}}, "reply": "2件の明細として追加します。"},
        {"user": "給料25万円を入れて", "command": {"name": "add_transaction", "arguments": {"date": "YYYY-MM-DD", "type": "income", "category": "給与", "memo": "給料", "amount": 250000}}, "reply": "収入として追加します。"},
        {"user": "今日のランチを900円に直して", "command": {"name": "update_transaction", "arguments": {"date": "YYYY-MM-DD", "memo": "ランチ", "amount": 900}}, "reply": "該当する明細を更新します。"},
        {"user": "昨日のコンビニを消して", "command": {"name": "delete_transaction", "arguments": {"date": "YYYY-MM-DD", "memo": "コンビニ"}}, "reply": "該当する明細を削除します。"},
        {"user": "今月の食費はいくら？", "command": {"name": "", "arguments": {}}, "reply": "今月の食費合計を集計して答えます。"},
    ],
}
