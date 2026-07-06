import { useEffect, useRef } from "react";
import {
  defineFeatureConnector,
  deleteFeatureConnector,
  getAppState,
  invokeConnectorAction,
  listFeatureConnectors,
  sendFeatureWorkerMessage,
  setAppState,
  type AppConnectorDefinition,
  type Attachment,
} from "../api";

function normalizeConnectorResult(result: Record<string, unknown>): Record<string, unknown> {
  const data = result?.data;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return { ...(data as Record<string, unknown>), ...result };
  }
  return result;
}

function normalizeExternalUrl(value: unknown): string | null {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) return null;
  try {
    const u = new URL(raw);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    u.username = "";
    u.password = "";
    return u.toString();
  } catch {
    return null;
  }
}

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

export async function deleteFeatureBlobs(feature: string): Promise<number> {
  const db = await _idb();
  const st = db.transaction(_IDB_STORE, "readwrite").objectStore(_IDB_STORE);
  const keys = (await _idbReq(st.getAllKeys())) as IDBValidKey[];
  const pre = `${feature}::`;
  let count = 0;
  for (const key of keys) {
    if (typeof key === "string" && key.startsWith(pre)) {
      await _idbReq(st.delete(key));
      count += 1;
    }
  }
  return count;
}

// A generated app runs in a SANDBOXED iframe (allow-scripts only: opaque origin,
// no access to our app/auth/Firestore, no localStorage, no network). We inject a
// tiny `AF` bridge so apps can persist their whole-state blob over postMessage:
//   const s = await AF.load();  await AF.save(s);
// `live=false` (chat preview) keeps persistence in-memory only.
const AF_PRELUDE = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:; connect-src 'none'; worker-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"><script>
(function(){
  var pending={}, seq=0;
  function req(op,payload){return new Promise(function(res){var id=++seq;pending[id]=res;parent.postMessage({__af:true,id:id,op:op,payload:payload},'*');});}
  // setChatVisible(bool): show/hide the app-chat panel (the shell renders it
  // outside the app). Per-SCREEN control — call it when navigating screens.
  // setChatContext(id,label): split the specialist worker's memory/thread by
  // screen or local work context. Call it when navigating between app screens.
  // saveBlob/loadBlob/listBlobs/deleteBlob: large files (PDF/image data URL or
  // base64 string) kept in the BROWSER (IndexedDB via the shell) — NOT in AF.save
  // (that state has a ~1MB cap). Per-device: loadBlob may return null on another
  // device, so always handle a missing blob gracefully.
  window.AF={
    load:function(){return req('load');},
    save:function(s){return req('save',s);},
    setChatVisible:function(v){parent.postMessage({__af_chat:!!v},'*');},
    setChatContext:function(id,label){parent.postMessage({__af_chat_context:{id:String(id||'default'),label:label?String(label):null}},'*');},
    saveBlob:function(name,data){return req('blob_save',{name:name,data:data});},
    loadBlob:function(name){return req('blob_load',{name:name});},
    listBlobs:function(){return req('blob_list');},
    deleteBlob:function(name){return req('blob_delete',{name:name});},
    // defineConnector/listConnectors/deleteConnector/api: app-scoped user-defined
    // external API access. The sandbox still has connect-src 'none'; generated
    // HTML registers fixed actions and then calls those names only.
    defineConnector:function(def){return req('connector_define',def||{});},
    listConnectors:function(){return req('connector_list');},
    deleteConnector:function(id){return req('connector_delete',{id:String(id||'')});},
    api:function(name,params){return req('api',{name:String(name||''),params:params||{}});},
    // openExternal(url): ask the shell to open a http(s) URL in a new tab with
    // noopener/noreferrer. Generated HTML must not call window.open directly.
    openExternal:function(url){return req('open_external',{url:String(url||'')});},
    // askWorker(text,{images}): let the APP itself invoke its Specialist Worker
    // (e.g. a 翻訳 button) — images are data: URLs. Returns {reply,command}; any
    // returned content command is also dispatched to applyAgentCommand.
    askWorker:function(text,opts){opts=opts||{};return req('ask_worker',{text:String(text||''),images:(opts.images||[])});}
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
  onChatContext,
}: {
  html: string;
  feature: string;
  title?: string;
  live?: boolean;
  command?: AgentCommand | null;
  onChatVisible?: (visible: boolean) => void;
  onChatContext?: (context: { id: string; label?: string | null }) => void;
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
      if (d && (d as { __af_chat_context?: unknown }).__af_chat_context) {
        const ctx = (d as { __af_chat_context: { id?: unknown; label?: unknown } }).__af_chat_context;
        onChatContext?.({
          id: String(ctx.id || "default"),
          label: ctx.label == null ? null : String(ctx.label),
        });
        return;
      }
      if (!d || !d.__af) return;
      const reply = (result: unknown) =>
        fr.contentWindow?.postMessage({ __af_reply: true, id: d.id, result }, "*");
      const bp = (d.payload as { name?: string; data?: unknown }) || {};
      const bname = String(bp.name ?? "");
      if (!live) {
        // Preview: feature isn't published yet. load/list → empty; askWorker n/a.
        if (d.op === "ask_worker") { reply({ reply: "（プレビューでは実行できません。公開後にお使いください）", command: null }); return; }
        if (d.op === "open_external") {
          const p = (d.payload as { url?: string }) || {};
          const safeUrl = normalizeExternalUrl(p.url);
          if (!safeUrl) { reply({ ok: false, error: "外部URLは http(s) のみ開けます。" }); return; }
          const opened = window.open(safeUrl, "_blank", "noopener,noreferrer");
          reply({ ok: !!opened, url: safeUrl });
          return;
        }
        if (d.op === "api" || String(d.op || "").startsWith("connector_")) { reply({ ok: false, error: "プレビューでは外部APIコネクタを実行できません。公開後にお使いください。" }); return; }
        reply(d.op === "load" || d.op === "blob_load" ? null : d.op === "blob_list" ? [] : true);
        return;
      }
      if (d.op === "ask_worker") {
        // The app invokes its OWN Specialist Worker (e.g. a 翻訳 button). Images are
        // data: URLs → Attachment(kind=image, base64). Dispatch any returned command.
        const p = (d.payload as { text?: string; images?: string[] }) || {};
        const atts: Attachment[] = (p.images || []).slice(0, 4).map((u, i) => {
          const mt = (/^data:([^;]+);base64,/.exec(u) || [])[1] || "image/png";
          const b64 = u.includes(",") ? u.slice(u.indexOf(",") + 1) : u;
          return { name: `img${i}.${(mt.split("/")[1] || "png")}`, mime: mt, kind: "image", content: b64 };
        });
        sendFeatureWorkerMessage(feature, p.text || "", atts)
          .then((res) => {
            if (res.command?.name) {
              fr.contentWindow?.postMessage(
                { __af_cmd: true, name: res.command.name, args: res.command.arguments ?? {} }, "*");
            }
            reply({ reply: res.reply?.text ?? "", command: res.command ?? null });
          })
          .catch(() => reply({ reply: "実行に失敗しました。少し待って再度お試しください。", command: null }));
        return;
      }
      if (d.op === "load") {
        getAppState(feature).then((s) => reply(s)).catch(() => reply(null));
      } else if (d.op === "save") {
        setAppState(feature, d.payload).then(() => reply(true)).catch(() => reply(false));
      } else if (d.op === "api") {
        const p = (d.payload as { name?: string; params?: Record<string, unknown> }) || {};
        invokeConnectorAction(feature, String(p.name || ""), p.params || {})
          .then((res) => reply(normalizeConnectorResult(res)))
          .catch((err) => reply({ ok: false, error: err instanceof Error ? err.message : String(err) }));
      } else if (d.op === "connector_define") {
        defineFeatureConnector(feature, d.payload as AppConnectorDefinition)
          .then(reply)
          .catch((err) => reply({ ok: false, error: err instanceof Error ? err.message : String(err) }));
      } else if (d.op === "connector_list") {
        listFeatureConnectors(feature)
          .then(reply)
          .catch((err) => reply({ items: [], error: err instanceof Error ? err.message : String(err) }));
      } else if (d.op === "connector_delete") {
        const p = (d.payload as { id?: string }) || {};
        deleteFeatureConnector(feature, String(p.id || ""))
          .then(reply)
          .catch((err) => reply({ ok: false, error: err instanceof Error ? err.message : String(err) }));
      } else if (d.op === "open_external") {
        const p = (d.payload as { url?: string }) || {};
        const safeUrl = normalizeExternalUrl(p.url);
        if (!safeUrl) {
          reply({ ok: false, error: "外部URLは http(s) のみ開けます。" });
          return;
        }
        const opened = window.open(safeUrl, "_blank", "noopener,noreferrer");
        reply({ ok: !!opened, url: safeUrl });
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
  }, [feature, live, onChatContext, onChatVisible]);

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
