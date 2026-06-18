import { useEffect, useRef, useState } from "react";
import type { User } from "firebase/auth";
import { disableFeature, getFeatureStates, getMe, resetAll, stopAllWorkers, type Me } from "../api";
import { isFirebaseConfigured, isGuestSession, signOutUser } from "../firebase";
import { ChatView } from "../views/ChatView";
import { GeneratedView } from "../views/GeneratedView";
import { ByokView } from "../views/ByokView";
import { StatusView } from "../views/StatusView";

// Admin is a SEPARATE app (frontend/admin.html), not reachable from here.
// EVERY feature (incl. task management) is AI-generated and rendered by the
// Generated View Renderer — no hard-coded screens.
type View =
  | { kind: "chat" }
  | { kind: "feature"; key: string }
  | { kind: "byok" }
  | { kind: "status" };

export function AppShell({ user }: { user: User | null }) {
  // Raw feature_states doc: { <feature>: "active"|"disabled", <feature>_title, _theme, _worker, ... }
  const [states, setStates] = useState<Record<string, string>>({});
  const [view, setView] = useState<View>({ kind: "chat" });
  const [prevView, setPrevView] = useState<View>({ kind: "chat" });
  const [denied, setDenied] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [appFullscreen, setAppFullscreen] = useState(false);
  const [restorePos, setRestorePos] = useState<{ x: number; y: number }>(() => {
    try {
      const parsed = JSON.parse(localStorage.getItem("af_restore_pos") || "null") as { x?: number; y?: number } | null;
      if (parsed && typeof parsed.x === "number" && typeof parsed.y === "number") {
        return { x: parsed.x, y: parsed.y };
      }
    } catch {
      /* ignore */
    }
    return { x: 24, y: 24 };
  });
  const restoreMovedRef = useRef(false);

  // Resizable / collapsible feature-list sidebar (persisted across reloads).
  const bodyRef = useRef<HTMLDivElement>(null);
  const draggingNav = useRef(false);
  const [navW, setNavW] = useState<number>(() => {
    const v = parseFloat(localStorage.getItem("af_nav_w") || "");
    return isFinite(v) && v >= 120 && v <= 2000 ? v : 240;
  });
  const [navOpen, setNavOpen] = useState<boolean>(() => localStorage.getItem("af_nav_open") !== "0");
  useEffect(() => { localStorage.setItem("af_nav_w", String(navW)); }, [navW]);
  useEffect(() => { localStorage.setItem("af_nav_open", navOpen ? "1" : "0"); }, [navOpen]);

  const navMovedRef = useRef(false);
  // Drag via WINDOW listeners (not element pointer-capture) so the drag survives
  // the divider ⇄ open-tab element swap — i.e. you can grab the › tab while
  // collapsed and drag it open in one motion.
  function beginNavDrag(e: React.PointerEvent) {
    e.preventDefault();
    draggingNav.current = true;
    navMovedRef.current = false;
    const move = (ev: PointerEvent) => {
      if (!bodyRef.current) return;
      navMovedRef.current = true;
      const rect = bodyRef.current.getBoundingClientRect();
      const w = ev.clientX - rect.left;
      if (w < 48) { setNavOpen(false); return; }   // drag fully in → collapse
      setNavOpen(true);                              // drag out → open + resize
      setNavW(Math.max(120, Math.min(rect.width - 80, w)));
    };
    const up = () => {
      draggingNav.current = false;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  function loadStates() {
    return getFeatureStates()
      .then((s) => setStates(s))
      .catch((e: unknown) => {
        const status = (e as { status?: number })?.status;
        if (status === 401 || status === 403) setDenied(true);
      });
  }

  useEffect(() => { void loadStates(); }, []);
  useEffect(() => { void getMe().then(setMe).catch(() => {}); }, []); // identity + flags

  function openOverlay(kind: "byok" | "status") {
    setAppFullscreen(false);
    setPrevView(view);
    setView({ kind });
  }
  useEffect(() => {
    if (view.kind !== "feature") setAppFullscreen(false);
  }, [view.kind]);
  useEffect(() => {
    localStorage.setItem("af_restore_pos", JSON.stringify(restorePos));
  }, [restorePos]);

  function beginRestoreDrag(e: React.PointerEvent) {
    e.preventDefault();
    restoreMovedRef.current = false;
    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);
    const rect = target.getBoundingClientRect();
    const offsetX = e.clientX - rect.left;
    const offsetY = e.clientY - rect.top;
    const move = (ev: PointerEvent) => {
      restoreMovedRef.current = true;
      const maxX = Math.max(0, window.innerWidth - rect.width - 8);
      const maxY = Math.max(0, window.innerHeight - rect.height - 8);
      setRestorePos({
        x: Math.max(8, Math.min(maxX, ev.clientX - offsetX)),
        y: Math.max(8, Math.min(maxY, ev.clientY - offsetY)),
      });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      try {
        target.releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  const [stoppingAll, setStoppingAll] = useState(false);
  async function handleStopAll() {
    if (stoppingAll) return;
    if (!confirm("実行中のワーカーをすべて停止します（全セッション）。よろしいですか？")) return;
    setStoppingAll(true);
    try {
      const r = await stopAllWorkers();
      alert(`停止しました（${r.stopped}件）。`);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setStoppingAll(false);
    }
  }

  if (denied) {
    return (
      <div className="centered">
        <h1>アクセス権限がありません</h1>
        <p className="muted">{user?.email ?? ""} はこのアプリの利用を許可されていません。</p>
        <button className="login" onClick={() => void signOutUser()}>別のアカウントでログアウト</button>
      </div>
    );
  }

  // Active features are keys whose value is exactly "active" (meta keys like
  // *_title / *_theme / *_worker / updated_at don't match and are filtered out).
  const activeFeatures = Object.keys(states).filter((k) => states[k] === "active");
  const titleOf = (f: string) => states[`${f}_title`] || (f === "task" ? "タスク管理" : f);
  const themeOf = (f: string) => states[`${f}_theme`] || "default";
  const iconOf = (_f: string) => "🧩";

  function goFeature(f: string) {
    setView({ kind: "feature", key: f });
  }

  function onFeatureActivated(feature: string) {
    void loadStates();
    goFeature(feature);
  }
  function onFeatureDisabled() {
    void loadStates();
    setView({ kind: "chat" });
  }

  // Rollback (human-only): soft-disable every active feature. Data is kept.
  async function handleRollback() {
    if (activeFeatures.length === 0) return;
    if (!confirm("AIが追加した機能を巻き戻しますか？（無効化のみ／データは保持されます）")) return;
    try {
      for (const f of activeFeatures) await disableFeature(f);
      await loadStates();
      setView({ kind: "chat" });
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleReset() {
    if (!confirm("【開発用】完全に初期化します。タスク・会話・登録・監査ログ・生成機能など全データを削除して、メインチャットだけの初期状態に戻します。よろしいですか？")) return;
    try {
      await resetAll();
      window.location.reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  const currentFeature = view.kind === "feature" ? view.key : null;
  const mainTheme = currentFeature ? themeOf(currentFeature) : "default";
  const navActive = (f: string) => view.kind === "feature" && view.key === f;
  const isLocalDev = !isFirebaseConfigured();
  const canFullscreenApp = view.kind === "feature";
  const guest = isGuestSession();

  return (
    <div className={appFullscreen ? "shell shell--app-fullscreen" : "shell"}>
      <header className="topbar">
        <div className="topbar__brand">AgentForge</div>
        <span className="topbar__tag">DevOps AI Agent Workbench</span>
        <span className="spacer" />
        <button
          className="stopall-top"
          title="実行中のワーカーをすべて停止（全セッション）"
          onClick={() => void handleStopAll()}
          disabled={stoppingAll}
        >
          ■ 全停止
        </button>
        <button
          className={view.kind === "status" ? "byok-top byok-top--active" : "byok-top"}
          title="ステータスモニタ（起動中ワーカー一覧）"
          onClick={() => openOverlay("status")}
        >
          📊 ステータス
        </button>
        {me?.feature_flags.byok_visible && (
          <button className="byok-top" title="自分のAPIキー設定（試作）" onClick={() => openOverlay("byok")}>
            🔑 API設定
          </button>
        )}
        {activeFeatures.length > 0 && (
          <button
            className="rollback-top"
            title="AIが追加した機能を取り消す（人間専用のControl Plane操作）"
            onClick={() => void handleRollback()}
          >
            ⟲ 機能を巻き戻す
          </button>
        )}
        <button
          className="fullscreen-top"
          title={canFullscreenApp ? "現在のアプリ画面を全画面化" : "ミニアプリを開いているときに使えます"}
          onClick={() => setAppFullscreen(true)}
          disabled={!canFullscreenApp}
        >
          ⛶ アプリ全画面化
        </button>
        {isLocalDev && (
          <button className="reset-top" title="【開発用】全データを削除して初期状態に戻す" onClick={() => void handleReset()}>
            🗑 初期化
          </button>
        )}
        {user && (
          <span className="topbar__user">
            {user.email}
            <button className="logout" onClick={() => void signOutUser()}>ログアウト</button>
          </span>
        )}
        {!user && guest && (
          <span className="topbar__user">
            ゲスト
            <button className="logout" onClick={() => { void signOutUser(); window.location.reload(); }}>ログアウト</button>
          </span>
        )}
        {isLocalDev && <span className="topbar__user">（ローカル: 認証なし）</span>}
      </header>

      <div className="body" ref={bodyRef}>
        {/* The sidebar collapses to width 0 but the divider/handle is ALWAYS
            rendered — the tab you grabbed to close stays put, so you can drag it
            straight back open (or click the chevron). */}
        <nav
          className={navOpen ? "sidebar" : "sidebar sidebar--collapsed"}
          style={{ width: navOpen ? navW : 0 }}
        >
          <div className="sidebar__label">機能</div>
          <button
            className={view.kind === "chat" ? "navitem navitem--active" : "navitem"}
            onClick={() => setView({ kind: "chat" })}
          >
            💬 メインチャット
          </button>
          {activeFeatures.map((f) => (
            <button key={f} className={navActive(f) ? "navitem navitem--active" : "navitem"} onClick={() => goFeature(f)}>
              {iconOf(f)} {titleOf(f)}
            </button>
          ))}
          {activeFeatures.length === 0 && (
            <div className="sidebar__hint">
              メインチャットで「タスク管理を追加して」→「反映して」で機能が増えます。
            </div>
          )}
        </nav>
        <div
          className="nav-divider"
          role="separator"
          aria-orientation="vertical"
          title="ドラッグで幅調整（左端まで引くと閉じる）／ボタンで開閉"
          onPointerDown={beginNavDrag}
        >
          <button
            className="nav-toggle"
            title={navOpen ? "機能リストを閉じる" : "クリックまたは右へドラッグで開く"}
            aria-label={navOpen ? "機能リストを閉じる" : "機能リストを開く"}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => setNavOpen((v) => !v)}
          >
            {navOpen ? "‹" : "›"}
          </button>
        </div>

        <main className="main" data-theme={mainTheme}>
          {/* ChatView stays MOUNTED across navigation (hidden, not unmounted) so a
              background design keeps polling and the conversation is never lost when
              you switch to a feature / API設定 and come back. */}
          <div className={view.kind === "chat" ? "main-pane" : "main-pane main-pane--hidden"}>
            <ChatView onFeatureActivated={onFeatureActivated} onFeatureDisabled={onFeatureDisabled} />
          </div>
          {view.kind === "feature" && (
            // After an in-place worker edit, refresh the sidebar (title/theme may
            // change) but STAY on the feature screen — the worker chat lives here.
            <GeneratedView feature={view.key} onEdited={() => void loadStates()} />
          )}
          {view.kind === "byok" && <ByokView onBack={() => setView(prevView)} />}
          {view.kind === "status" && <StatusView onBack={() => setView(prevView)} />}
        </main>
      </div>

      {appFullscreen && (
        <button
          className="app-restore"
          style={{ left: restorePos.x, top: restorePos.y }}
          title="ドラッグで移動 / クリックで元に戻す"
          onPointerDown={beginRestoreDrag}
          onClick={() => {
            if (restoreMovedRef.current) return;
            setAppFullscreen(false);
          }}
        >
          ↙ 元に戻す
        </button>
      )}
    </div>
  );
}
