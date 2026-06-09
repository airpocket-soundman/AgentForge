import { useEffect, useRef } from "react";
import { getAppState, setAppState } from "../api";

// A generated app runs in a SANDBOXED iframe (allow-scripts only: opaque origin,
// no access to our app/auth/Firestore, no localStorage, no network). We inject a
// tiny `AF` bridge so apps can persist their whole-state blob over postMessage:
//   const s = await AF.load();  await AF.save(s);
// `live=false` (chat preview) keeps persistence in-memory only.
const AF_PRELUDE = `<script>
(function(){
  var pending={}, seq=0;
  function req(op,payload){return new Promise(function(res){var id=++seq;pending[id]=res;parent.postMessage({__af:true,id:id,op:op,payload:payload},'*');});}
  window.AF={load:function(){return req('load');},save:function(s){return req('save',s);}};
  window.addEventListener('message',function(e){var d=e.data;if(!d||!d.__af_reply)return;var cb=pending[d.id];if(cb){delete pending[d.id];cb(d.result);}});
  try{var __ls=window.localStorage;__ls.setItem('__af_probe','1');__ls.removeItem('__af_probe');}catch(_){var m={};try{Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null;},setItem:function(k,v){m[k]=String(v);},removeItem:function(k){delete m[k];},clear:function(){m={};},key:function(i){return Object.keys(m)[i]||null;},get length(){return Object.keys(m).length;}}});}catch(__){}}
})();
<\/script>`;

export function withPrelude(html: string): string {
  const m = html.match(/<head[^>]*>/i);
  if (m && m.index != null) {
    const at = m.index + m[0].length;
    return html.slice(0, at) + AF_PRELUDE + html.slice(at);
  }
  return AF_PRELUDE + html;
}

export function AppFrame({
  html,
  feature,
  title,
  live = true,
}: {
  html: string;
  feature: string;
  title?: string;
  live?: boolean;
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      const fr = frameRef.current;
      if (!fr || e.source !== fr.contentWindow) return; // only our iframe
      const d = e.data as { __af?: boolean; id?: number; op?: string; payload?: unknown };
      if (!d || !d.__af) return;
      const reply = (result: unknown) =>
        fr.contentWindow?.postMessage({ __af_reply: true, id: d.id, result }, "*");
      if (!live) {
        // Preview: don't touch the backend (feature isn't published yet).
        reply(d.op === "load" ? null : true);
        return;
      }
      if (d.op === "load") {
        getAppState(feature).then((s) => reply(s)).catch(() => reply(null));
      } else if (d.op === "save") {
        setAppState(feature, d.payload).then(() => reply(true)).catch(() => reply(false));
      }
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [feature, live]);

  return (
    <iframe
      ref={frameRef}
      className="gen-app-frame"
      title={title ?? feature}
      sandbox="allow-scripts"
      srcDoc={html ? withPrelude(html) : ""}
    />
  );
}
