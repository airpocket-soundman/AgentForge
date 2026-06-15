import { useEffect, useRef, useState } from "react";
import type { User } from "firebase/auth";
import { disableFeature, getFeatureStates, getMe, resetAll, stopAllWorkers, type Me } from "../api";
import { isFirebaseConfigured, signOutUser } from "../firebase";
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

  // Resizable / collapsible feature-list sidebar (persisted across reloads).
  const bodyRef = useRef<HTMLDivElement>(null);
  const draggingNav = useRef(false);
  const [navW, setNavW] = useState<number>(() => {
    const v = parseFloat(localStorage.getItem("af_nav_w") || "");
    return isFinite(v) && v >= 90 && v <= 720 ? v : 240;
  });
  const [navOpen, setNavOpen] = useState<boolean>(() => localStorage.getItem("af_nav_open") !== "0");
  useEffect(() => { localStorage.setItem("af_nav_w", String(navW)); }, [navW]);
  useEffect(() => { localStorage.setItem("af_nav_open", navOpen ? "1" : "0"); }, [navOpen]);

  function onNavDragStart(e: React.PointerEvent) {
    e.preventDefault();
    draggingNav.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }
  function onNavDragMove(e: React.PointerEvent) {
    if (!draggingNav.current || !bodyRef.current) return;
    const rect = bodyRef.current.getBoundingClientRect();
    // Wide range: as narrow as 90px, up to 80% of the window (max 720px) — but
    // always leave room for the app area.
    const hi = Math.min(720, rect.width - 280);
    setNavW(Math.max(90, Math.min(hi, e.clientX - rect.left)));
  }
  function onNavDragEnd(e: React.PointerEvent) {
    draggingNav.current = false;
    try { (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId); } catch { /* ignore */ }
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
    setPrevView(view);
    setView({ kind });
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

  return (
    <div className="shell">
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
        <button className="reset-top" title="【開発用】全データを削除して初期状態に戻す" onClick={() => void handleReset()}>
          🗑 初期化
        </button>
        {user && (
          <span className="topbar__user">
            {user.email}
            <button className="logout" onClick={() => void signOutUser()}>ログアウト</button>
          </span>
        )}
        {!isFirebaseConfigured() && <span className="topbar__user">（ローカル: 認証なし）</span>}
      </header>

      <div className="body" ref={bodyRef}>
        {navOpen ? (
          <>
            <nav className="sidebar" style={{ width: navW }}>
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
              title="ドラッグで機能リストの幅を調整"
              onPointerDown={onNavDragStart}
              onPointerMove={onNavDragMove}
              onPointerUp={onNavDragEnd}
            >
              <button
                className="nav-collapse"
                title="機能リストを閉じる"
                aria-label="機能リストを閉じる"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => setNavOpen(false)}
              >
                ‹
              </button>
            </div>
          </>
        ) : (
          <button
            className="nav-open"
            title="機能リストを開く"
            aria-label="機能リストを開く"
            onClick={() => setNavOpen(true)}
          >
            ›
          </button>
        )}

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
    </div>
  );
}
