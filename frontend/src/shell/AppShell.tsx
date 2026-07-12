import { useEffect, useRef, useState } from "react";
import type { User } from "firebase/auth";
import { activateMainChatContext, clearGuestSession, getConversationState, getFeatureStates, getMe, resetAll, rollbackFeature, setProjectId, stopAllWorkers, type Me } from "../api";
import { isFirebaseConfigured, signOutUser } from "../firebase";
import { ChatView } from "../views/ChatView";
import { GeneratedView } from "../views/GeneratedView";
import { ByokView } from "../views/ByokView";
import { StatusView } from "../views/StatusView";
import { loadUserSettings, UserSettingsView, type UserSettings } from "../views/UserSettingsView";
import { poweredByLabel, PRODUCT } from "../product";
import { FeatureSidebar } from "./FeatureSidebar";

// Admin is a SEPARATE app (frontend/admin.html), not reachable from here.
// EVERY feature (incl. task management) is AI-generated and rendered by the
// Generated View Renderer — no hard-coded screens.
type View =
  | { kind: "chat" }
  | { kind: "feature"; key: string }
  | { kind: "byok" }
  | { kind: "status" };

export function AppShell({ user, onShowHome }: { user: User | null; onShowHome?: () => void }) {
  // Raw feature_states doc: { <feature>: "active"|"disabled", <feature>_title, _theme, _worker, ... }
  const [states, setStates] = useState<Record<string, string>>({});
  const [view, setView] = useState<View>({ kind: "chat" });
  const [prevView, setPrevView] = useState<View>({ kind: "chat" });
  const [denied, setDenied] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [userSettings, setUserSettings] = useState<UserSettings>(() => loadUserSettings());
  const [userSettingsOpen, setUserSettingsOpen] = useState(false);
  const [identityReady, setIdentityReady] = useState(false);
  const [appFullscreen, setAppFullscreen] = useState(false);
  const [requestedChatContext, setRequestedChatContext] = useState<string | null>(null);
  const [lockedFeatures, setLockedFeatures] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem("af_locked_features") || "[]") as string[]);
    } catch {
      return new Set();
    }
  });
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

  useEffect(() => {
    void getMe()
      .then((m) => {
        setMe(m);
        setProjectId(m.project_id);
        return loadStates();
      })
      .catch((e: unknown) => {
        const status = (e as { status?: number })?.status;
        if (status === 401 || status === 403) setDenied(true);
      })
      .finally(() => setIdentityReady(true));
  }, []); // identity + flags + project scope

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

  useEffect(() => {
    if (lockedFeatures.size === 0) return;
    const syncLocks = async () => {
      const finished: string[] = [];
      await Promise.all([...lockedFeatures].map(async (feature) => {
        try {
          const contextId = localStorage.getItem(`af_locked_pipeline:${feature}`) || `app_${feature}`;
          const state = await getConversationState(undefined, contextId);
          if (!state.building && state.stage === "idle") finished.push(feature);
        } catch {
          /* keep locked until the next successful status check */
        }
      }));
      finished.forEach((feature) => setFeatureLocked(feature, false));
    };
    void syncLocks();
    const id = window.setInterval(() => void syncLocks(), 3000);
    return () => window.clearInterval(id);
  }, [lockedFeatures]);

  if (denied) {
    return (
      <div className="centered">
        <h1>アクセス権限がありません</h1>
        <p className="muted">{user?.email ?? ""} はこのアプリの利用を許可されていません。</p>
        <button className="login" onClick={() => { clearGuestSession(); void signOutUser(); }}>別のアカウントでログアウト</button>
      </div>
    );
  }

  if (!identityReady) {
    return <div className="centered">読み込み中…</div>;
  }

  // Active features are keys whose value is exactly "active" (meta keys like
  // *_title / *_theme / *_worker / updated_at don't match and are filtered out).
  const activeFeatures = Object.keys(states).filter((k) => states[k] === "active");
  const titleOf = (f: string) => states[`${f}_title`] || (f === "task" ? "タスク管理" : f);
  const themeOf = (f: string) => states[`${f}_theme`] || "default";
  const iconOf = (_f: string) => "🧩";

  function goFeature(f: string) {
    if (lockedFeatures.has(f)) return;
    setView({ kind: "feature", key: f });
  }

  function setFeatureLocked(feature: string, locked: boolean) {
    setLockedFeatures((current) => {
      const next = new Set(current);
      if (locked) next.add(feature); else next.delete(feature);
      if (!locked) localStorage.removeItem(`af_locked_pipeline:${feature}`);
      localStorage.setItem("af_locked_features", JSON.stringify([...next]));
      return next;
    });
  }

  async function openAppPipeline(feature: string, contextId: string) {
    setFeatureLocked(feature, true);
    localStorage.setItem(`af_locked_pipeline:${feature}`, contextId);
    localStorage.setItem("af_main_chat_context", contextId);
    setRequestedChatContext(contextId);
    setAppFullscreen(false);
    setView({ kind: "chat" });
    await activateMainChatContext(contextId).catch(() => {});
  }

  function onFeatureActivated(feature: string) {
    void loadStates();
    goFeature(feature);
  }
  function onFeatureDisabled() {
    void loadStates();
    setView({ kind: "chat" });
  }

  // Rollback (human-only): undo the latest changed feature only. Data is kept.
  async function handleRollback() {
    if (activeFeatures.length === 0) return;
    const target = states.last_changed_feature && activeFeatures.includes(states.last_changed_feature)
      ? states.last_changed_feature
      : activeFeatures[activeFeatures.length - 1];
    const title = titleOf(target);
    if (!confirm(`直近の変更「${title}」を巻き戻しますか？\n作成直後の機能なら左メニューから外れますが、保存データは保持されます。`)) return;
    try {
      await rollbackFeature(target);
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
  const isLocalDev = !isFirebaseConfigured();
  const canReset = import.meta.env.DEV || Boolean(me?.is_admin);
  const canFullscreenApp = view.kind === "feature";
  const userLabel = me?.is_guest ? `ゲスト: ${me.email}` : user ? user.email || "ユーザー" : "ローカルユーザー";
  const avatarSource = me?.email || user?.email || "A";
  const avatarText = (userSettings.iconText || avatarSource.slice(0, 1) || "A").slice(0, 2);
  function openUserSettings() {
    setAppFullscreen(false);
    setUserSettingsOpen(true);
  }
  return (
    <div className={appFullscreen ? "shell shell--app-fullscreen" : "shell"}>
      <header className="topbar">
        <div className="topbar__brand">{PRODUCT.displayName}</div>
        <span className="topbar__tag">{poweredByLabel}</span>
        <span className="spacer" />
        {onShowHome && (
          <button
            className="byok-top"
            title="説明トップページを開く"
            data-tooltip="説明トップページを開きます。サインイン済みでもアプリ画面に戻れます。"
            aria-label="説明トップページを開く"
            onClick={onShowHome}
          >
            トップ
          </button>
        )}
        <button
          className="stopall-top"
          title="実行中のワーカーをすべて停止（全セッション）"
          data-tooltip="実行中のワーカーを全セッションで停止します。長時間止まらない作業の回収に使います。"
          aria-label="実行中のワーカーをすべて停止"
          onClick={() => void handleStopAll()}
          disabled={stoppingAll}
        >
          ■ 全停止
        </button>
        <button
          className={view.kind === "status" ? "byok-top byok-top--active" : "byok-top"}
          title="ステータスモニタ（起動中ワーカー一覧）"
          data-tooltip="ワーカー状態、実行中の作業、パイプラインログ、変更履歴を確認します。"
          aria-label="ステータスモニタを開く"
          onClick={() => openOverlay("status")}
        >
          📊 ステータス
        </button>
        {me?.feature_flags.byok_visible && (
          <button
            className="byok-top"
            title="自分のAPIキー設定（試作）"
            data-tooltip="LLM APIキー設定画面を開きます。デモ期間中は機能停止中です。"
            aria-label="API設定を開く"
            onClick={() => openOverlay("byok")}
          >
            🔑 API設定
          </button>
        )}
        {activeFeatures.length > 0 && (
          <button
            className="rollback-top"
            title="AIが追加した機能を取り消す（人間専用のControl Plane操作）"
            data-tooltip="直近で変更された機能を前の公開版へ戻します。公開済みスナップショットから復元します。"
            aria-label="直近の機能変更を巻き戻す"
            onClick={() => void handleRollback()}
          >
            ⟲ 機能を巻き戻す
          </button>
        )}
        <button
          className="fullscreen-top"
          title={canFullscreenApp ? "現在のアプリ画面を全画面化" : "ミニアプリを開いているときに使えます"}
          data-tooltip={canFullscreenApp ? "現在開いているミニアプリを画面いっぱいに表示します。" : "ミニアプリを開いているときだけ全画面化できます。"}
          aria-label="アプリ全画面化"
          onClick={() => setAppFullscreen(true)}
          disabled={!canFullscreenApp}
        >
          ⛶ アプリ全画面化
        </button>
        {canReset && (
          <button
            className="reset-top"
            title="【開発用】全データを削除して初期状態に戻す"
            data-tooltip="開発用の完全初期化です。会話、生成機能、状態、監査ログを削除します。"
            aria-label="開発用に全データを初期化する"
            onClick={() => void handleReset()}
          >
            🗑 初期化
          </button>
        )}
        <span className="topbar__user">
          <button
            className={userSettingsOpen ? "topbar-user-button topbar-user-button--active" : "topbar-user-button"}
            title="ユーザー設定を開く"
            data-tooltip="ユーザーアイコン、呼び名、デモ中のAPIキー表示設定を開きます。"
            aria-label="ユーザー設定を開く"
            onClick={openUserSettings}
          >
            <span className={userSettings.iconImageDataUrl ? "topbar-user-avatar topbar-user-avatar--image" : "topbar-user-avatar"} style={userSettings.iconImageDataUrl ? undefined : { background: userSettings.iconColor }}>
              {userSettings.iconImageDataUrl ? <img src={userSettings.iconImageDataUrl} alt="" /> : avatarText}
            </span>
            <span className="topbar-user-label">{userLabel}</span>
          </button>
          {(user || me?.is_guest) && (
            <button
              className="logout"
              title="現在のアカウントからログアウト"
              data-tooltip="現在のアカウントまたはゲスト環境からログアウトします。"
              aria-label="ログアウト"
              onClick={() => {
                clearGuestSession();
                void signOutUser().finally(() => {
                  if (me?.is_guest) window.location.reload();
                });
              }}
            >
              ログアウト
            </button>
          )}
          {isLocalDev && <span className="topbar-local-label">認証なし</span>}
        </span>
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
          <FeatureSidebar
            projectId={me?.project_id || "default"}
            features={activeFeatures}
            titleOf={titleOf}
            iconOf={iconOf}
            activeFeature={currentFeature}
            onOpen={goFeature}
            lockedFeatures={lockedFeatures}
          />
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
            <ChatView
              onFeatureActivated={onFeatureActivated}
              onFeatureDisabled={onFeatureDisabled}
              requestedContext={requestedChatContext}
              onAppPipelineFinished={(contextId) => {
                const feature = [...lockedFeatures].find(
                  (item) => localStorage.getItem(`af_locked_pipeline:${item}`) === contextId,
                );
                if (feature) setFeatureLocked(feature, false);
              }}
            />
          </div>
          {view.kind === "feature" && (
            // After an in-place worker edit, refresh the sidebar (title/theme may
            // change) but STAY on the feature screen — the worker chat lives here.
            <GeneratedView
              feature={view.key}
              onEdited={() => void loadStates()}
              onBuildStarted={(feature, contextId) => void openAppPipeline(feature, contextId)}
            />
          )}
          {view.kind === "byok" && <ByokView onBack={() => setView(prevView)} />}
          {view.kind === "status" && <StatusView onBack={() => setView(prevView)} />}
        </main>
      </div>

      {userSettingsOpen && (
        <div className="settings-modal-backdrop" role="presentation" onMouseDown={() => setUserSettingsOpen(false)}>
          <div className="settings-modal" role="dialog" aria-modal="true" aria-label="ユーザー設定" onMouseDown={(e) => e.stopPropagation()}>
            <UserSettingsView
              onClose={() => setUserSettingsOpen(false)}
              userEmail={userLabel}
              onSaved={(settings) => setUserSettings(settings)}
            />
          </div>
        </div>
      )}

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
