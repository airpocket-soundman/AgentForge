import { useEffect, useRef } from "react";
import { getAppState, setAppState } from "../api";

// --- Browser-local binary store (IndexedDB) for AF.saveBlob/loadBlob ----------
// Large files (PDFs, images) can't go in AF.save: that whole-state blob is a
// Firestore doc (≈1MB cap). So big originals live in the user's browser via
// IndexedDB — zero cost, no backend surface, dev=prod parity, and the bytes never
// leave the device. Trade-off: per-browser/device only (not synced like state),
// so apps must tolerate a blob being absent on another device.
const _IDB_DB = "agentforge_blobs";
const _IDB_STORE = "blobs";

function _idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(_IDB_DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(_IDB_STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
function _idbReq<T>(op: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    op.onsuccess = () => resolve(op.result);
    op.onerror = () => reject(op.error);
  });
}
async function blobSave(feature: string, name: string, data: unknown): Promise<boolean> {
  const db = await _idb();
  const st = db.transaction(_IDB_STORE, "readwrite").objectStore(_IDB_STORE);
  await _idbReq(st.put(data, `${feature}::${name}`));
  return true;
}
async function blobLoad(feature: string, name: string): Promise<unknown> {
  const db = await _idb();
  const st = db.transaction(_IDB_STORE, "readonly").objectStore(_IDB_STORE);
  const v = await _idbReq(st.get(`${feature}::${name}`));
  return v ?? null;
}
async function blobDelete(feature: string, name: string): Promise<boolean> {
  const db = await _idb();
  const st = db.transaction(_IDB_STORE, "readwrite").objectStore(_IDB_STORE);
  await _idbReq(st.delete(`${feature}::${name}`));
  return true;
}
async function blobList(feature: string): Promise<string[]> {
  const db = await _idb();
  const st = db.transaction(_IDB_STORE, "readonly").objectStore(_IDB_STORE);
  const keys = (await _idbReq(st.getAllKeys())) as IDBValidKey[];
  const pre = `${feature}::`;
  return keys.filter((k) => typeof k === "string" && k.startsWith(pre)).map((k) => (k as string).slice(pre.length));
}

// A generated app runs in a SANDBOXED iframe (allow-scripts only: opaque origin,
// no access to our app/auth/Firestore, no localStorage, no network). We inject a
// tiny `AF` bridge so apps can persist their whole-state blob over postMessage:
//   const s = await AF.load();  await AF.save(s);
// `live=false` (chat preview) keeps persistence in-memory only.
const AF_PRELUDE = `<script>
(function(){
  var pending={}, seq=0;
  function req(op,payload){return new Promise(function(res){var id=++seq;pending[id]=res;parent.postMessage({__af:true,id:id,op:op,payload:payload},'*');});}
  // setChatVisible(bool): show/hide the app-chat panel (the shell renders it
  // outside the app). Per-SCREEN control — call it when navigating screens.
  // saveBlob/loadBlob/listBlobs/deleteBlob: large files (PDF/image data URL or
  // base64 string) kept in the BROWSER (IndexedDB via the shell) — NOT in AF.save
  // (that state has a ~1MB cap). Per-device: loadBlob may return null on another
  // device, so always handle a missing blob gracefully.
  window.AF={
    load:function(){return req('load');},
    save:function(s){return req('save',s);},
    setChatVisible:function(v){parent.postMessage({__af_chat:!!v},'*');},
    saveBlob:function(name,data){return req('blob_save',{name:name,data:data});},
    loadBlob:function(name){return req('blob_load',{name:name});},
    listBlobs:function(){return req('blob_list');},
    deleteBlob:function(name){return req('blob_delete',{name:name});}
  };
  window.addEventListener('message',function(e){var d=e.data;if(!d||!d.__af_reply)return;var cb=pending[d.id];if(cb){delete pending[d.id];cb(d.result);}});
  try{var __ls=window.localStorage;__ls.setItem('__af_probe','1');__ls.removeItem('__af_probe');}catch(_){var m={};try{Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null;},setItem:function(k,v){m[k]=String(v);},removeItem:function(k){delete m[k];},clear:function(){m={};},key:function(i){return Object.keys(m)[i]||null;},get length(){return Object.keys(m).length;}}});}catch(__){}}
  // Agent content command: the feature worker maps NL to a command; the parent
  // posts it here and the app runs its own window.applyAgentCommand(name,args).
  window.addEventListener('message',function(e){var d=e.data;if(!d||!d.__af_cmd)return;try{if(typeof window.applyAgentCommand==='function'){window.applyAgentCommand(d.name,d.args||{});}}catch(_){}});
})();
<\/script>`;

export interface AgentCommand {
  name: string;
  args?: Record<string, unknown>;
  nonce: number; // bump to re-dispatch the same command
}

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
  command,
  onChatVisible,
}: {
  html: string;
  feature: string;
  title?: string;
  live?: boolean;
  command?: AgentCommand | null;
  onChatVisible?: (visible: boolean) => void;
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);

  // Dispatch an agent content command into the running app.
  useEffect(() => {
    if (!command) return;
    frameRef.current?.contentWindow?.postMessage(
      { __af_cmd: true, name: command.name, args: command.args ?? {} },
      "*",
    );
  }, [command]);

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      const fr = frameRef.current;
      if (!fr || e.source !== fr.contentWindow) return; // only our iframe
      const d = e.data as {
        __af?: boolean; __af_chat?: boolean; id?: number; op?: string;
        payload?: { name?: string; data?: unknown } | unknown;
      };
      if (d && d.__af_chat !== undefined) {
        onChatVisible?.(!!d.__af_chat); // per-screen app-chat visibility signal
        return;
      }
      if (!d || !d.__af) return;
      const reply = (result: unknown) =>
        fr.contentWindow?.postMessage({ __af_reply: true, id: d.id, result }, "*");
      const bp = (d.payload as { name?: string; data?: unknown }) || {};
      const bname = String(bp.name ?? "");
      if (!live) {
        // Preview: don't persist (feature isn't published). load/list → empty.
        reply(d.op === "load" || d.op === "blob_load" ? null : d.op === "blob_list" ? [] : true);
        return;
      }
      if (d.op === "load") {
        getAppState(feature).then((s) => reply(s)).catch(() => reply(null));
      } else if (d.op === "save") {
        setAppState(feature, d.payload).then(() => reply(true)).catch(() => reply(false));
      } else if (d.op === "blob_save") {
        blobSave(feature, bname, bp.data).then(reply).catch(() => reply(false));
      } else if (d.op === "blob_load") {
        blobLoad(feature, bname).then(reply).catch(() => reply(null));
      } else if (d.op === "blob_list") {
        blobList(feature).then(reply).catch(() => reply([]));
      } else if (d.op === "blob_delete") {
        blobDelete(feature, bname).then(reply).catch(() => reply(false));
      }
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [feature, live, onChatVisible]);

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
