import { useEffect, useState } from "react";
import type { User } from "firebase/auth";
import {
  isFirebaseConfigured,
  onAuthChange,
  signOutUser,
  signInWithGoogle,
} from "./firebase";
import { getPublicConfig } from "./api";
import { AppShell } from "./shell/AppShell";

function LandingNav({
  user,
  showGuestCta,
  onSignIn,
  onGuestLogin,
  onOpenApp,
  onSignOut,
}: {
  user: User | null;
  showGuestCta: boolean;
  onSignIn: () => void;
  onGuestLogin: () => void;
  onOpenApp: () => void;
  onSignOut: () => void;
}) {
  return (
    <header className="landing-nav">
      <button className="landing-brand" onClick={() => window.location.hash = "home"}>AgentForge</button>
      <nav className="landing-links" aria-label="メイン">
        <a href="https://findy.notion.site/devops-ai-agent-hackathon-2026" target="_blank" rel="noreferrer">DevOps × AI Agent</a>
        <a href="#features">特徴</a>
        <a href="#flow">Pipeline</a>
        <a href="#architecture">Architecture</a>
        <a href="#implementation">実装</a>
        <a href="#safety">安全性</a>
      </nav>
      <div className="landing-auth">
        {user ? (
          <>
            <span className="landing-user">{user.photoURL && <img src={user.photoURL} alt="" />} {user.email}</span>
            <button className="landing-secondary" onClick={onOpenApp}>アプリを開く</button>
            <button className="landing-primary" onClick={onSignOut}>Sign out</button>
          </>
        ) : (
          <>
            {showGuestCta && <button className="landing-judge-nav" onClick={onGuestLogin}>審査員用ゲストログイン</button>}
            <span className="landing-usericon" aria-hidden="true" />
            <button className="landing-secondary" onClick={onSignIn}>Sign in</button>
            <button className="landing-primary" onClick={onSignIn}>Sign up</button>
          </>
        )}
      </div>
    </header>
  );
}

function LandingPage({
  user,
  showGuestCta,
  error,
  onSignIn,
  onGuestLogin,
  onOpenApp,
  onSignOut,
}: {
  user: User | null;
  showGuestCta: boolean;
  error: string | null;
  onSignIn: () => void;
  onGuestLogin: () => void;
  onOpenApp: () => void;
  onSignOut: () => void;
}) {
  const [zoomedFlow, setZoomedFlow] = useState<"pipeline" | "architecture" | null>(null);

  useEffect(() => {
    if (!zoomedFlow) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setZoomedFlow(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [zoomedFlow]);

  return (
    <div className="landing">
      <LandingNav user={user} showGuestCta={showGuestCta} onSignIn={onSignIn} onGuestLogin={onGuestLogin} onOpenApp={onOpenApp} onSignOut={onSignOut} />

      <main>
        <section className="landing-hero">
          <div className="landing-copy">
            <a
              className="landing-hackathon"
              href="https://findy.notion.site/devops-ai-agent-hackathon-2026"
              target="_blank"
              rel="noreferrer"
            >
              DevOps × AI Agent
            </a>
            <div className="landing-kicker">DevOps AI Agent Workbench</div>
            <h1>会話だけで、自分専用アプリを作って育てる。</h1>
            <p>
              AgentForge は、非エンジニアでもメインチャットからミニアプリを作成・改変・公開・巻き戻しできる、
              自己拡張型の AI ワークベンチです。メモ、スケジュール、タスク管理などのデフォルトアプリから始めて、
              UI や機能を自分好みに育てることも、まったく新しいアプリを作ることもできます。
              裏側では複数のワーカー、Safety Harness、Agent Harness が、設計から検証、承認、監査までを分担します。
            </p>
            <div className="landing-actions">
              {user ? (
                <button className="landing-primary landing-primary--large" onClick={onOpenApp}>アプリ画面へ</button>
              ) : (
                <button className="landing-primary landing-primary--large" onClick={onSignIn}>アプリを開く</button>
              )}
            </div>
            {!user && showGuestCta && (
              <button className="landing-judge-big" onClick={onGuestLogin}>
                審査員用ゲストログイン
                <span>Google アカウントで個別のゲスト環境に入ります</span>
              </button>
            )}
            {!user && (
              <p className="landing-note">許可リスト外の Google アカウントは、ゲストとして個別環境で試せます。</p>
            )}
            {error && <div className="error">{error}</div>}
          </div>
          <div className="landing-visual" aria-label="AgentForge の画面イメージ">
            <img src="/agentforge_app_screen.png" alt="AgentForge のアプリ画面構成" />
          </div>
        </section>

        <section className="landing-band" id="beginner">
          <div className="landing-section-head">
            <span>Beginner View</span>
            <h2>ゼロから作らなくても、まず使いながら育てられる</h2>
            <p>
              いきなり白紙からアプリを設計する必要はありません。用意されたデフォルトアプリを選び、
              「色を変えて」「項目を増やして」「この操作を追加して」のように話すだけで、
              AI が下書き、実装、検証を進め、最後に人間が確認して反映します。
            </p>
          </div>
          <div className="landing-simple-flow" aria-label="AgentForge の基本利用フロー">
            <div className="landing-simple-step landing-simple-step--talk">
              <strong>1. 選ぶ / 話す</strong>
              <span>デフォルトアプリを選ぶか、作りたいものや直したい点をそのまま伝えます。</span>
            </div>
            <div className="landing-flow-arrow" aria-hidden="true">→</div>
            <div className="landing-simple-step landing-simple-step--build">
              <strong>2. AI が直す / 作る</strong>
              <span>UI の変更、機能追加、新規作成をワーカーが設計、コード生成、動作確認、レビューします。</span>
            </div>
            <div className="landing-flow-arrow" aria-hidden="true">→</div>
            <div className="landing-simple-step landing-simple-step--approve">
              <strong>3. 確認して反映</strong>
              <span>プレビューで確認し、「反映して」と承認したものだけが公開されます。</span>
            </div>
          </div>
        </section>

        <section className="landing-band" id="features">
          <h2>話すだけで DevOps を回す</h2>
          <div className="landing-grid">
            <div><b>選んで育てる</b><span>メモ、スケジュール、タスク管理などを起点に、見た目や操作を自分用へ変えられます。</span></div>
            <div><b>機能を足す</b><span>「この項目を追加」「こう表示して」など、欲しい機能を会話で実装できます。</span></div>
            <div><b>ためす</b><span>Tester と Reviewer が動作と規約を確認し、未完成の公開を防ぎます。</span></div>
            <div><b>とどける</b><span>プレビュー確認後、「反映して」で公開。履歴から巻き戻しもできます。</span></div>
          </div>
        </section>

        <section className="landing-band" id="flow">
          <div className="landing-section-head">
            <span>Pipeline</span>
            <h2>自然言語を、検証済みミニアプリへ変換するパイプライン</h2>
            <p>
              AgentForge は、ユーザーの発話を単発のコード生成に投げるだけではありません。依頼を
              <code>task_id</code> 付きの作業単位に変換し、設計、生成、検証、レビュー、プレビュー、公開承認までを
              1本のパイプラインとして管理します。公開前の安全判定は Safety Harness が担い、
              途中経過、失敗理由、リトライ、承認状態は Agent Harness に残し、
              ユーザーには Receptor 経由で短く報告します。
            </p>
          </div>
          <div className="landing-pipeline-layout">
            <button
              type="button"
              className="flow-zoom-trigger"
              onClick={() => setZoomedFlow("pipeline")}
              aria-label="パイプラインのフロー図を拡大表示"
            >
              <div className="detail-svg-frame"><VerticalPipelineFlowSvg /></div>
              <span>クリックで拡大</span>
            </button>
            <div className="detail-flow-notes detail-flow-notes--side">
              <div><b>キー技術: MCP 的 request / report</b><span>ワーカー間の連携は <code>task_id</code> と <code>in_reply_to</code> で相関します。LLM の会話を非同期ジョブとして扱うことで、停止、再開、差し戻しを制御できます。</span></div>
              <div><b>キー技術: Preview-first deploy</b><span>生成物はまず pending としてプレビューに出ます。公開済み版には触れず、ユーザーが「反映して」と言った時だけ active 化します。</span></div>
              <div><b>キー技術: Safety Harness</b><span>Tester / Reviewer の結果と禁止 API 検査を統合し、通過した候補だけを preview / publish へ進めます。判断の証跡は Agent Harness に残します。</span></div>
            </div>
          </div>
        </section>

        <section className="landing-band" id="architecture">
          <div className="landing-section-head">
            <span>Architecture</span>
            <h2>役割分離されたエージェント構造</h2>
            <p>
              AgentForge は、1つの AI に全権を渡しません。ユーザーと話す Receptor、設計と生成を担う Orchestrator、
              実行検証の Tester、規約判定の Reviewer、公開後のミニアプリを操作する Specialist Worker を分離します。
              その外側で Control Plane、Safety Harness、Agent Harness、Sandbox、Version 管理が副作用を制御します。
            </p>
          </div>
          <button
            type="button"
            className="flow-zoom-trigger flow-zoom-trigger--center"
            onClick={() => setZoomedFlow("architecture")}
            aria-label="エージェント構造図を拡大表示"
          >
            <div className="detail-svg-frame"><VerticalArchitectureFlowSvg /></div>
            <span>クリックで拡大</span>
          </button>
          <div className="landing-arch-reading" aria-label="アーキテクチャ図の読み方">
            <div className="landing-arch-zones">
              <h3>図の4つの領域</h3>
              <div><b>User Experience</b><span>ユーザーが触る場所。メインチャットで依頼し、ミニアプリを iframe で使います。</span></div>
              <div><b>Worker Layer</b><span>LLM が判断する場所。Receptor、Orchestrator、Tester / Reviewer が役割を分けて働きます。</span></div>
              <div><b>Runtime Sandbox</b><span>生成物を実行する場所。HTML は sandbox iframe に閉じ込め、保存は <code>AF.load/save</code> だけにします。</span></div>
              <div><b>Observability</b><span>判断と変更を残す場所。Agent Harness、Version、Audit が後から追える証跡を持ちます。</span></div>
            </div>
            <div className="landing-arch-spine">
              <h3>中央の制御軸</h3>
              <div><b>Safety Harness</b><span>Tester / Reviewer と禁止 API 検査をまとめ、公開前に通してよい候補かを判定します。</span></div>
              <div><b>Control Plane</b><span>公開、承認、版管理、巻き戻しなどの強い副作用を決定的 API と人間承認に閉じ込めます。</span></div>
              <div><b>Specialist Worker</b><span>公開後のミニアプリ内データだけを操作します。構造変更はメインチャットへ取り次ぎます。</span></div>
            </div>
          </div>
        </section>

        <section className="landing-band" id="implementation">
          <div className="landing-section-head">
            <span>Implementation</span>
            <h2>生成物は「画面」だけではなく、操作可能なアプリ契約として作る</h2>
            <p>
              AgentForge は、自然言語から見た目だけを作るのではなく、公開後に Specialist Worker が継続操作できる
              contract まで生成します。HTML、state、commands、Worker prompt、評価ケースを同時に設計し、
              生成されたアプリを「使える画面」から「育てられる道具」にします。
            </p>
          </div>
          <div className="detail-grid">
            <div><b>View artifact</b><span><code>&lt;!DOCTYPE html&gt;</code> から始まる自己完結 HTML。外部 CDN、fetch、cookie、localStorage なしで sandbox 実行します。</span></div>
            <div><b>State contract</b><span>予定、タスク、家計簿、メモなどは <code>worker_state_mode=state/hybrid</code> と <code>state_schema</code> を生成します。</span></div>
            <div><b>Command surface</b><span><code>window.applyAgentCommand(name,args)</code> と <code>commands[]</code> を一致させ、UI 操作を安全に公開します。</span></div>
            <div><b>Worker prompt pack</b><span>利用可能 API、聞き返し方針、危険操作方針、自然言語例をアプリごとに Specialist Worker へ渡します。</span></div>
            <div><b>Worker Eval</b><span>一括削除、曖昧な対象、異常値、担当外の構造変更など、失敗しやすい指示をテストケース化します。</span></div>
            <div><b>Version metadata</b><span>feature、title、theme、manifest 参照、承認 ID、公開版スナップショットを Control Plane が管理します。</span></div>
            <div><b>Runtime context</b><span>複数画面や詳細画面では <code>AF.setChatContext()</code> でアプリチャットの文脈を分けます。</span></div>
            <div><b>Blob strategy</b><span>大きなファイルは <code>AF.saveBlob/loadBlob</code> に逃がし、通常 state のサイズ肥大化を防ぎます。</span></div>
          </div>
        </section>

        <section className="landing-band" id="safety">
          <div className="landing-section-head">
            <span>Quality Gates</span>
            <h2>公開前に止めるべきものを止める</h2>
            <p>
              Tester は実際の動作、Reviewer は規約、Safety Harness は禁止 API・外部リソース・Worker 契約を統合して確認します。
              通過しない候補は preview に止め、公開済み版には触りません。
            </p>
          </div>
          <div className="detail-grid">
            <div><b>Sandbox / Persistence</b><span>外部通信や localStorage に依存せず、状態は <code>AF.load/save</code> で復元できること。</span></div>
            <div><b>Worker operability</b><span>主要操作が <code>commands</code> または <code>state_schema</code> で表現され、自然言語から到達できること。</span></div>
            <div><b>UX fidelity</b><span>要求をフォームだけで代替せず、実際に使える UI とレスポンシブ性を満たすこと。</span></div>
            <div><b>Human gates</b><span>受付、設計、公開を分け、本公開・巻き戻し・削除は Control Plane と人間承認に閉じ込めること。</span></div>
            <div><b>Preview / Version</b><span>未通過の成果物は active 化せず、公開ごとのスナップショットから即時に巻き戻せること。</span></div>
            <div><b>Deletion / Audit</b><span>削除は対象確認後に完全削除し、操作証跡を監査ログに残すこと。</span></div>
          </div>
        </section>
      </main>

      {zoomedFlow && (
        <div className="flow-modal" role="dialog" aria-modal="true" aria-label="フロー図の拡大表示" onClick={() => setZoomedFlow(null)}>
          <div className="flow-modal__panel" onClick={(event) => event.stopPropagation()}>
            <div className="flow-modal__head">
              <h2>{zoomedFlow === "pipeline" ? "Pipeline Flow" : "Agent Architecture"}</h2>
              <button type="button" onClick={() => setZoomedFlow(null)} aria-label="拡大表示を閉じる">閉じる</button>
            </div>
            <div className="flow-modal__body">
              <div className={`detail-svg-frame flow-modal__svg-frame ${zoomedFlow === "pipeline" ? "flow-modal__svg-frame--pipeline" : ""}`}>
                {zoomedFlow === "pipeline" ? <VerticalPipelineFlowSvg /> : <VerticalArchitectureFlowSvg />}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function PipelineFlowSvg() {
  return (
    <svg className="detail-svg" viewBox="0 0 1180 640" role="img" aria-label="ミニアプリ制作パイプラインのフロー図">
      <defs>
        <marker id="pipelineArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#596174" />
        </marker>
        <marker id="pipelineWarnArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#b93d4f" />
        </marker>
      </defs>

      <rect className="svg-bg" x="1" y="1" width="1178" height="638" rx="18" />

      <g className="svg-node svg-user">
        <rect x="40" y="76" width="140" height="66" rx="10" />
        <text x="110" y="102">ユーザー</text>
        <text x="110" y="124">作って / 直して</text>
      </g>
      <line className="svg-line" x1="180" y1="109" x2="230" y2="109" markerEnd="url(#pipelineArrow)" />

      <g className="svg-node svg-worker">
        <rect x="230" y="76" width="150" height="66" rx="10" />
        <text x="305" y="102">Receptor</text>
        <text x="305" y="124">内容を整理</text>
      </g>
      <line className="svg-line" x1="380" y1="109" x2="430" y2="109" markerEnd="url(#pipelineArrow)" />

      <g className="svg-decision">
        <path d="M490 68 L550 109 L490 150 L430 109 Z" />
        <text x="490" y="105">依頼は</text>
        <text x="490" y="124">明確?</text>
      </g>
      <line className="svg-line" x1="550" y1="109" x2="604" y2="109" markerEnd="url(#pipelineArrow)" />
      <text className="svg-label" x="568" y="96">Yes</text>

      <g className="svg-node svg-worker">
        <rect x="604" y="76" width="160" height="66" rx="10" />
        <text x="684" y="102">Orchestrator</text>
        <text x="684" y="124">設計案を作成</text>
      </g>
      <line className="svg-line" x1="764" y1="109" x2="814" y2="109" markerEnd="url(#pipelineArrow)" />

      <g className="svg-decision">
        <path d="M874 68 L934 109 L874 150 L814 109 Z" />
        <text x="874" y="105">設計</text>
        <text x="874" y="124">承認?</text>
      </g>
      <path className="svg-line" d="M874 150 C874 198 212 198 212 282 L212 298" markerEnd="url(#pipelineArrow)" />
      <text className="svg-label" x="882" y="181">Yes</text>

      <g className="svg-node svg-build">
        <rect x="130" y="298" width="164" height="70" rx="10" />
        <text x="212" y="326">コード生成</text>
        <text x="212" y="348">HTML / API / Worker</text>
      </g>
      <line className="svg-line" x1="294" y1="333" x2="356" y2="333" markerEnd="url(#pipelineArrow)" />

      <g className="svg-node svg-check">
        <rect x="356" y="298" width="168" height="70" rx="10" />
        <text x="440" y="326">Tester / Reviewer</text>
        <text x="440" y="348">動作と規約を確認</text>
      </g>
      <line className="svg-line" x1="524" y1="333" x2="586" y2="333" markerEnd="url(#pipelineArrow)" />

      <g className="svg-decision svg-decision-warn">
        <path d="M646 290 L706 333 L646 376 L586 333 Z" />
        <text x="646" y="329">合格?</text>
        <text x="646" y="348">Pass?</text>
      </g>
      <line className="svg-line" x1="706" y1="333" x2="766" y2="333" markerEnd="url(#pipelineArrow)" />
      <text className="svg-label" x="725" y="320">Yes</text>

      <g className="svg-node svg-preview">
        <rect x="766" y="298" width="146" height="70" rx="10" />
        <text x="839" y="326">プレビュー</text>
        <text x="839" y="348">ユーザー確認</text>
      </g>
      <line className="svg-line" x1="912" y1="333" x2="970" y2="333" markerEnd="url(#pipelineArrow)" />

      <g className="svg-decision">
        <path d="M1030 290 L1090 333 L1030 376 L970 333 Z" />
        <text x="1030" y="329">反映</text>
        <text x="1030" y="348">承認?</text>
      </g>
      <path className="svg-line" d="M1030 376 C1030 420 1030 430 1030 456" markerEnd="url(#pipelineArrow)" />
      <text className="svg-label" x="1044" y="408">Yes</text>

      <g className="svg-node svg-release">
        <rect x="948" y="456" width="164" height="70" rx="10" />
        <text x="1030" y="484">Control Plane</text>
        <text x="1030" y="506">公開 / 版保存</text>
      </g>

      <g className="svg-node svg-note">
        <rect x="428" y="204" width="142" height="58" rx="10" />
        <text x="499" y="228">聞き返し</text>
        <text x="499" y="248">内容を具体化</text>
      </g>
      <path className="svg-line svg-return" d="M458 136 C386 170 386 214 428 233" markerEnd="url(#pipelineWarnArrow)" />
      <text className="svg-label svg-label-warn" x="386" y="178">No</text>
      <path className="svg-line svg-return" d="M428 250 C270 268 132 222 110 142" markerEnd="url(#pipelineWarnArrow)" />

      <path className="svg-line svg-return" d="M844 136 C776 176 706 202 684 142" markerEnd="url(#pipelineWarnArrow)" />
      <text className="svg-label svg-label-warn" x="770" y="164">修正</text>

      <path className="svg-line svg-return" d="M620 364 C552 438 286 438 212 368" markerEnd="url(#pipelineWarnArrow)" />
      <text className="svg-label svg-label-warn" x="410" y="454">NG: 指摘を反映して再生成</text>

      <path className="svg-line svg-return" d="M810 368 C730 520 250 520 212 368" markerEnd="url(#pipelineWarnArrow)" />
      <text className="svg-label svg-label-warn" x="480" y="535">プレビュー修正: 設計またはコードへ戻る</text>

      <g className="svg-node svg-timeout">
        <rect x="604" y="456" width="194" height="70" rx="10" />
        <text x="701" y="484">停滞時</text>
        <text x="701" y="506">停止 / 待つ / 再トライ</text>
      </g>
      <path className="svg-line svg-dash" d="M684 142 C706 230 730 370 701 456" markerEnd="url(#pipelineArrow)" />
      <path className="svg-line svg-dash" d="M440 368 C480 430 560 472 604 491" markerEnd="url(#pipelineArrow)" />
    </svg>
  );
}

export function ArchitectureFlowSvg() {
  return (
    <svg className="detail-svg" viewBox="0 0 1180 600" role="img" aria-label="AgentForge アーキテクチャのフロー図">
      <defs>
        <marker id="archArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#596174" />
        </marker>
        <marker id="archReturnArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#b93d4f" />
        </marker>
      </defs>

      <rect className="svg-bg" x="1" y="1" width="1178" height="598" rx="18" />
      <rect className="svg-boundary" x="38" y="52" width="248" height="150" rx="14" />
      <text className="svg-boundary-title" x="58" y="78">User Experience</text>

      <g className="svg-node svg-user">
        <rect x="68" y="104" width="188" height="66" rx="10" />
        <text x="162" y="130">ユーザー</text>
        <text x="162" y="152">メインチャット / ミニアプリ</text>
      </g>

      <line className="svg-line" x1="256" y1="137" x2="326" y2="137" markerEnd="url(#archArrow)" />
      <g className="svg-node svg-worker">
        <rect x="326" y="104" width="154" height="66" rx="10" />
        <text x="403" y="130">Receptor</text>
        <text x="403" y="152">受付と進捗報告</text>
      </g>
      <line className="svg-line" x1="480" y1="137" x2="548" y2="137" markerEnd="url(#archArrow)" />

      <g className="svg-node svg-worker">
        <rect x="548" y="104" width="164" height="66" rx="10" />
        <text x="630" y="130">Orchestrator</text>
        <text x="630" y="152">設計と生成</text>
      </g>
      <line className="svg-line" x1="712" y1="137" x2="780" y2="137" markerEnd="url(#archArrow)" />

      <g className="svg-node svg-check">
        <rect x="780" y="104" width="170" height="66" rx="10" />
        <text x="865" y="130">Tester / Reviewer</text>
        <text x="865" y="152">検証と規約判定</text>
      </g>
      <line className="svg-line" x1="950" y1="137" x2="1016" y2="137" markerEnd="url(#archArrow)" />

      <g className="svg-node svg-release">
        <rect x="1016" y="104" width="128" height="66" rx="10" />
        <text x="1080" y="130">Control</text>
        <text x="1080" y="152">Plane</text>
      </g>

      <rect className="svg-boundary" x="504" y="64" width="682" height="178" rx="14" />
      <text className="svg-boundary-title" x="524" y="90">Build and Release Control</text>

      <g className="svg-node svg-note">
        <rect x="548" y="306" width="180" height="70" rx="10" />
        <text x="638" y="334">Agent Harness</text>
        <text x="638" y="356">判断とイベントを記録</text>
      </g>
      <path className="svg-line svg-dash" d="M403 170 C430 250 548 278 638 306" markerEnd="url(#archArrow)" />
      <path className="svg-line svg-dash" d="M630 170 C640 224 642 270 638 306" markerEnd="url(#archArrow)" />
      <path className="svg-line svg-dash" d="M865 170 C810 244 728 282 638 306" markerEnd="url(#archArrow)" />

      <g className="svg-node svg-preview">
        <rect x="810" y="306" width="182" height="70" rx="10" />
        <text x="901" y="334">Sandbox iframe</text>
        <text x="901" y="356">AF.load / AF.save</text>
      </g>
      <path className="svg-line" d="M1080 170 C1070 250 1010 306 992 334" markerEnd="url(#archArrow)" />

      <g className="svg-node svg-worker">
        <rect x="810" y="450" width="182" height="70" rx="10" />
        <text x="901" y="478">Specialist Worker</text>
        <text x="901" y="500">アプリ内データ操作</text>
      </g>
      <path className="svg-line" d="M901 376 C901 408 901 426 901 450" markerEnd="url(#archArrow)" />
      <path className="svg-line svg-return" d="M810 486 C690 530 520 470 630 170" markerEnd="url(#archReturnArrow)" />
      <text className="svg-label svg-label-warn" x="620" y="522">構造変更はメインチャットへ取り次ぎ</text>

      <g className="svg-node svg-note">
        <rect x="310" y="450" width="188" height="70" rx="10" />
        <text x="404" y="478">Version / Audit</text>
        <text x="404" y="500">公開版と操作履歴</text>
      </g>
      <path className="svg-line svg-dash" d="M1080 170 C1034 390 620 486 498 486" markerEnd="url(#archArrow)" />
      <path className="svg-line svg-return" d="M498 472 C700 420 890 398 1016 154" markerEnd="url(#archReturnArrow)" />
      <text className="svg-label svg-label-warn" x="650" y="430">巻き戻しは版から即時復元</text>

      <g className="svg-node svg-timeout">
        <rect x="68" y="306" width="188" height="70" rx="10" />
        <text x="162" y="334">停滞検知</text>
        <text x="162" y="356">Receptor がユーザー確認</text>
      </g>
      <path className="svg-line svg-dash" d="M403 170 C320 230 230 278 162 306" markerEnd="url(#archArrow)" />
    </svg>
  );
}

function VerticalPipelineFlowSvg() {
  return (
    <svg className="detail-svg detail-svg--vertical" viewBox="0 0 900 1280" role="img" aria-label="ミニアプリ制作パイプラインの縦型フロー図">
      <defs>
        <marker id="pipelineVArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#596174" />
        </marker>
        <marker id="pipelineVWarnArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#b93d4f" />
        </marker>
      </defs>

      <rect className="svg-bg" x="1" y="1" width="898" height="1278" rx="18" />
      <rect className="svg-boundary" x="276" y="24" width="348" height="1198" rx="18" />
      <text className="svg-boundary-title" x="304" y="52">Main pipeline</text>
      <rect className="svg-boundary" x="646" y="144" width="210" height="760" rx="18" />
      <text className="svg-boundary-title" x="670" y="172">Return paths</text>
      <rect className="svg-boundary" x="46" y="546" width="210" height="188" rx="18" />
      <text className="svg-boundary-title" x="72" y="574">Stall handling</text>

      <g className="svg-node svg-user">
        <rect x="320" y="66" width="260" height="64" rx="10" />
        <text x="450" y="92">ユーザー</text>
        <text x="450" y="114">作って / 直して</text>
      </g>
      <line className="svg-line" x1="450" y1="130" x2="450" y2="164" markerEnd="url(#pipelineVArrow)" />

      <g className="svg-node svg-worker">
        <rect x="320" y="164" width="260" height="64" rx="10" />
        <text x="450" y="190">Receptor</text>
        <text x="450" y="212">内容整理と進捗報告</text>
      </g>
      <line className="svg-line" x1="450" y1="228" x2="450" y2="262" markerEnd="url(#pipelineVArrow)" />

      <g className="svg-decision">
        <path d="M450 262 L532 316 L450 370 L368 316 Z" />
        <text x="450" y="312">依頼は</text>
        <text x="450" y="331">明確?</text>
      </g>
      <line className="svg-line" x1="450" y1="370" x2="450" y2="406" markerEnd="url(#pipelineVArrow)" />
      <text className="svg-label" x="462" y="394">Yes</text>

      <g className="svg-node svg-worker">
        <rect x="320" y="406" width="260" height="64" rx="10" />
        <text x="450" y="432">Orchestrator</text>
        <text x="450" y="454">設計案を作成</text>
      </g>
      <line className="svg-line" x1="450" y1="470" x2="450" y2="504" markerEnd="url(#pipelineVArrow)" />

      <g className="svg-decision">
        <path d="M450 504 L532 558 L450 612 L368 558 Z" />
        <text x="450" y="554">設計</text>
        <text x="450" y="573">承認?</text>
      </g>
      <line className="svg-line" x1="450" y1="612" x2="450" y2="648" markerEnd="url(#pipelineVArrow)" />
      <text className="svg-label" x="462" y="636">Yes</text>

      <g className="svg-node svg-build">
        <rect x="320" y="648" width="260" height="70" rx="10" />
        <text x="450" y="676">コード生成</text>
        <text x="450" y="698">HTML / API / Worker</text>
      </g>
      <line className="svg-line" x1="450" y1="718" x2="450" y2="754" markerEnd="url(#pipelineVArrow)" />

      <g className="svg-node svg-check">
        <rect x="320" y="754" width="260" height="70" rx="10" />
        <text x="450" y="782">Tester / Reviewer</text>
        <text x="450" y="804">動作と規約を確認</text>
      </g>
      <line className="svg-line" x1="450" y1="824" x2="450" y2="860" markerEnd="url(#pipelineVArrow)" />

      <g className="svg-decision svg-decision-warn">
        <path d="M450 860 L532 914 L450 968 L368 914 Z" />
        <text x="450" y="910">合格?</text>
        <text x="450" y="929">Pass?</text>
      </g>
      <line className="svg-line" x1="450" y1="968" x2="450" y2="1004" markerEnd="url(#pipelineVArrow)" />
      <text className="svg-label" x="462" y="992">Yes</text>

      <g className="svg-node svg-preview">
        <rect x="320" y="1004" width="260" height="70" rx="10" />
        <text x="450" y="1032">プレビュー</text>
        <text x="450" y="1054">ユーザー確認</text>
      </g>
      <line className="svg-line" x1="450" y1="1074" x2="450" y2="1110" markerEnd="url(#pipelineVArrow)" />

      <g className="svg-decision">
        <path d="M450 1110 L532 1164 L450 1218 L368 1164 Z" />
        <text x="450" y="1160">反映</text>
        <text x="450" y="1179">承認?</text>
      </g>
      <line className="svg-line" x1="532" y1="1164" x2="654" y2="1164" markerEnd="url(#pipelineVArrow)" />
      <text className="svg-label" x="560" y="1150">Yes</text>

      <g className="svg-node svg-release">
        <rect x="654" y="1130" width="178" height="70" rx="10" />
        <text x="743" y="1158">Control Plane</text>
        <text x="743" y="1180">公開 / 版保存</text>
      </g>

      <g className="svg-node svg-note">
        <rect x="666" y="272" width="168" height="66" rx="10" />
        <text x="750" y="298">聞き返し</text>
        <text x="750" y="320">内容を具体化</text>
      </g>
      <path className="svg-line svg-return" d="M532 316 C590 316 612 305 666 305" markerEnd="url(#pipelineVWarnArrow)" />
      <path className="svg-line svg-return" d="M666 320 C608 376 522 248 450 228" markerEnd="url(#pipelineVWarnArrow)" />
      <text className="svg-label svg-label-warn" x="584" y="298">No</text>

      <g className="svg-node svg-note">
        <rect x="666" y="516" width="168" height="66" rx="10" />
        <text x="750" y="542">修正指示</text>
        <text x="750" y="564">設計案へ戻る</text>
      </g>
      <path className="svg-line svg-return" d="M532 558 C602 558 616 549 666 549" markerEnd="url(#pipelineVWarnArrow)" />
      <path className="svg-line svg-return" d="M666 532 C632 480 584 442 580 438" markerEnd="url(#pipelineVWarnArrow)" />

      <g className="svg-node svg-note">
        <rect x="666" y="858" width="168" height="70" rx="10" />
        <text x="750" y="886">NG</text>
        <text x="750" y="908">指摘を反映して再生成</text>
      </g>
      <path className="svg-line svg-return" d="M532 914 C604 914 616 893 666 893" markerEnd="url(#pipelineVWarnArrow)" />
      <path className="svg-line svg-return" d="M666 874 C618 764 600 686 580 683" markerEnd="url(#pipelineVWarnArrow)" />

      <g className="svg-node svg-note">
        <rect x="666" y="998" width="168" height="70" rx="10" />
        <text x="750" y="1026">プレビュー修正</text>
        <text x="750" y="1048">設計またはコードへ戻る</text>
      </g>
      <path className="svg-line svg-return" d="M580 1039 C620 1039 636 1033 666 1033" markerEnd="url(#pipelineVWarnArrow)" />
      <path className="svg-line svg-return" d="M666 1014 C620 780 598 448 580 438" markerEnd="url(#pipelineVWarnArrow)" />

      <g className="svg-node svg-timeout">
        <rect x="66" y="600" width="170" height="76" rx="10" />
        <text x="151" y="630">停滞時</text>
        <text x="151" y="652">停止 / 待つ / 再トライ</text>
      </g>
      <path className="svg-line svg-dash" d="M320 438 C250 470 210 540 186 600" markerEnd="url(#pipelineVArrow)" />
      <path className="svg-line svg-dash" d="M320 683 C270 670 236 654 236 638" markerEnd="url(#pipelineVArrow)" />
      <path className="svg-line svg-dash" d="M320 789 C250 760 212 706 186 676" markerEnd="url(#pipelineVArrow)" />
    </svg>
  );
}

function VerticalArchitectureFlowSvg() {
  return (
    <svg className="detail-svg architecture-svg" viewBox="0 0 900 720" role="img" aria-label="AgentForge アーキテクチャ構造図">
      <defs>
        <marker id="archVArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#596174" />
        </marker>
        <marker id="archVReturnArrow" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#b93d4f" />
        </marker>
      </defs>

      <rect className="svg-bg" x="1" y="1" width="898" height="718" rx="18" />
      <rect className="svg-boundary" x="28" y="42" width="270" height="236" rx="18" />
      <text className="svg-boundary-title" x="58" y="70">User Experience</text>
      <rect className="svg-boundary" x="602" y="42" width="270" height="236" rx="18" />
      <text className="svg-boundary-title" x="638" y="70">Worker Layer</text>
      <rect className="svg-boundary" x="28" y="442" width="270" height="222" rx="18" />
      <text className="svg-boundary-title" x="58" y="470">Runtime Sandbox</text>
      <rect className="svg-boundary" x="602" y="442" width="270" height="222" rx="18" />
      <text className="svg-boundary-title" x="638" y="470">Observability</text>

      <g className="svg-node svg-user">
        <rect x="54" y="96" width="212" height="62" rx="10" />
        <text x="160" y="122">メインチャット</text>
        <text x="160" y="144">Receptor と会話</text>
      </g>

      <g className="svg-node svg-user">
        <rect x="54" y="184" width="212" height="62" rx="10" />
        <text x="160" y="210">ミニアプリ</text>
        <text x="160" y="232">iframe で表示</text>
      </g>

      <g className="svg-node svg-worker">
        <rect x="630" y="82" width="220" height="58" rx="10" />
        <text x="740" y="106">Receptor</text>
        <text x="740" y="128">受付と進捗共有</text>
      </g>

      <g className="svg-node svg-worker">
        <rect x="630" y="158" width="220" height="58" rx="10" />
        <text x="740" y="182">Orchestrator</text>
        <text x="740" y="204">設計と生成</text>
      </g>

      <g className="svg-node svg-check">
        <rect x="630" y="234" width="220" height="58" rx="10" />
        <text x="740" y="258">Tester / Reviewer</text>
        <text x="740" y="280">検証と規約判定</text>
      </g>

      <g className="svg-node svg-release">
        <rect x="302" y="270" width="296" height="98" rx="14" />
        <text x="450" y="308">Control Plane</text>
        <text x="450" y="332">公開・承認・版管理</text>
        <text x="450" y="354">強い副作用はここだけ</text>
      </g>

      <g className="svg-node svg-check">
        <rect x="302" y="150" width="296" height="76" rx="12" />
        <text x="450" y="180">Safety Harness</text>
        <text x="450" y="202">公開前の最終安全判定</text>
      </g>

      <g className="svg-node svg-preview">
        <rect x="54" y="494" width="212" height="62" rx="10" />
        <text x="160" y="520">Sandbox iframe</text>
        <text x="160" y="542">生成 HTML を隔離</text>
      </g>

      <g className="svg-node svg-preview">
        <rect x="54" y="580" width="212" height="62" rx="10" />
        <text x="160" y="606">AF.load / AF.save</text>
        <text x="160" y="628">保存はブリッジ経由</text>
      </g>

      <g className="svg-node svg-worker">
        <rect x="338" y="504" width="224" height="70" rx="10" />
        <text x="450" y="532">Specialist Worker</text>
        <text x="450" y="554">担当アプリ内だけ操作</text>
      </g>

      <g className="svg-node svg-note">
        <rect x="630" y="494" width="220" height="62" rx="10" />
        <text x="740" y="520">Agent Harness</text>
        <text x="740" y="542">判断と成果物を記録</text>
      </g>

      <g className="svg-node svg-note">
        <rect x="630" y="580" width="220" height="62" rx="10" />
        <text x="740" y="606">Version / Audit</text>
        <text x="740" y="628">公開版と操作履歴</text>
      </g>

      <path className="svg-line" d="M256 127 C300 142 330 166 316 188" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M644 111 C604 126 582 150 584 188" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M644 187 C616 190 602 192 584 195" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M644 263 C608 254 588 236 568 226" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M450 226 L450 270" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M316 319 C270 330 238 438 180 494" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M450 368 L450 504" markerEnd="url(#archVArrow)" />
      <path className="svg-line" d="M584 319 C640 342 710 438 740 494" markerEnd="url(#archVArrow)" />
      <path className="svg-line svg-dash" d="M256 215 C322 238 354 274 366 303" markerEnd="url(#archVArrow)" />
      <path className="svg-line svg-dash" d="M160 556 L160 580" markerEnd="url(#archVArrow)" />
      <path className="svg-line svg-dash" d="M256 611 C296 606 330 584 354 552" markerEnd="url(#archVArrow)" />
      <path className="svg-line svg-dash" d="M546 539 C584 532 612 526 644 525" markerEnd="url(#archVArrow)" />
      <path className="svg-line svg-return" d="M644 611 C562 672 374 672 256 611" markerEnd="url(#archVReturnArrow)" />
      <text className="svg-label svg-label-warn" x="392" y="680">巻き戻しは LLM 不使用で版から復元</text>

      <text className="svg-label" x="338" y="116">要求</text>
      <text className="svg-label" x="580" y="116">指示/報告</text>
      <text className="svg-label" x="590" y="392">証跡</text>
      <text className="svg-label" x="238" y="392">隔離実行</text>
    </svg>
  );
}

function PipelineDetailPage({
  user,
  showGuestCta,
  onSignIn,
  onGuestLogin,
  onOpenApp,
  onSignOut,
}: {
  user: User | null;
  showGuestCta: boolean;
  onSignIn: () => void;
  onGuestLogin: () => void;
  onOpenApp: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="landing">
      <LandingNav user={user} showGuestCta={showGuestCta} onSignIn={onSignIn} onGuestLogin={onGuestLogin} onOpenApp={onOpenApp} onSignOut={onSignOut} />
      <main className="detail-page">
        <a className="detail-back" href="#home">トップへ戻る</a>
        <section className="detail-hero">
          <span>Pipeline Detail</span>
          <h1>ミニアプリが生まれて公開されるまで</h1>
          <p>
            AgentForge のパイプラインは、自然言語から単発の HTML を出すだけではありません。
            画面、永続化 state、Specialist Worker 用の操作 API、評価ケース、承認ゲート、監査ログまでを
            1つの生成単位として扱い、非エンジニアが使い続けられるミニアプリへ変換します。
          </p>
        </section>

        <section className="detail-section">
          <h2>フロー図</h2>
          <div className="detail-svg-frame"><VerticalPipelineFlowSvg /></div>
          <div className="detail-flow-notes">
            <div><b>設計が違う</b><span>ユーザーの修正指示で設計案に戻ります。</span></div>
            <div><b>検証 NG</b><span>Tester / Reviewer の指摘を反映してコード生成へ戻ります。</span></div>
            <div><b>停滞</b><span>Receptor が停止、待機、再トライをユーザーに確認します。</span></div>
          </div>
        </section>

        <section className="detail-section">
          <h2>全体フロー</h2>
          <div className="detail-timeline" aria-label="詳細なパイプライン">
            <div><b>1. Intent capture</b><span>Receptor がユーザー発話を要求、質問、相談、アプリ操作に分類し、曖昧な目的語や危険操作は聞き返します。</span></div>
            <div><b>2. Task envelope</b><span><code>task_id</code>、要求要約、対象 feature、承認状態、期限目安を持つ作業単位として Harness に記録します。</span></div>
            <div><b>3. Design plan</b><span>Orchestrator が画面構造、保存 state、操作 API、Specialist Worker プロンプト、受け入れ条件を設計します。</span></div>
            <div><b>4. Human gate</b><span>「これで作って」までコード生成しません。設計差分はここで人間が確認できます。</span></div>
            <div><b>5. Artifact build</b><span>単体 HTML、<code>commands</code>、<code>state_schema</code>、<code>worker_eval_cases</code>、manifest を生成します。</span></div>
            <div><b>6. Dual gate</b><span>Tester は実行検証、Reviewer は規約・安全境界を静的確認し、どちらか NG なら再生成へ戻します。</span></div>
            <div><b>7. Preview deploy</b><span>生成物は pending としてプレビューに出し、公開済み版には触れません。修正指示は同じ作業文脈で戻します。</span></div>
            <div><b>8. Publish control</b><span>「反映して」後に Control Plane が active 化し、版スナップショットと監査ログを残します。</span></div>
          </div>
        </section>

        <section className="detail-section">
          <h2>生成される技術成果物</h2>
          <div className="detail-grid">
            <div><b>View artifact</b><span><code>&lt;!DOCTYPE html&gt;</code> から始まる自己完結 HTML。外部 CDN、fetch、localStorage に依存しない sandbox 前提の UI です。</span></div>
            <div><b>State contract</b><span>予定、タスク、家計簿などのデータ中心アプリでは <code>worker_state_mode=state/hybrid</code> と <code>state_schema</code> を生成します。</span></div>
            <div><b>Command surface</b><span><code>window.applyAgentCommand(name,args)</code> と <code>commands[]</code> を対応させ、Worker が安全に UI やデータを操作できるようにします。</span></div>
            <div><b>Worker prompt pack</b><span>役割、API 仕様、聞き返し方針、危険操作方針、自然言語例をアプリごとに Specialist Worker へ渡します。</span></div>
            <div><b>Eval cases</b><span>一括削除、曖昧な対象、異常値、担当外の構造変更など、失敗しやすい指示を Tester が検証できる形で持ちます。</span></div>
            <div><b>Version metadata</b><span>feature、title、theme、manifest 参照、公開版スナップショット、承認 ID を Control Plane が扱います。</span></div>
            <div><b>Audit events</b><span>受付、設計、生成、レビュー、検証、プレビュー、公開、巻き戻し、削除を <code>pipeline_runs</code> に記録します。</span></div>
            <div><b>Acceptance summary</b><span>ユーザーには raw trace ではなく、合否、残課題、反映対象を短く要約して提示します。</span></div>
          </div>
        </section>

        <section className="detail-section detail-two-col">
          <div>
            <h2>ワーカー間プロトコル</h2>
            <p>
              ワーカー連携は会話の投げっぱなしではなく、MCP 的な request/report で相関します。
              指示は <code>task_id</code>、<code>message_id</code>、<code>from/to</code>、<code>intent</code>、<code>payload</code>、<code>context_refs</code> を持ち、
              報告は <code>in_reply_to</code>、<code>status</code>、<code>result</code>、<code>findings</code>、<code>usage</code> を返します。
            </p>
            <p>
              これにより、非同期実行、休止中ワーカーの rehydrate、失敗時の再開、レビュー差し戻しを同じ制御モデルで扱えます。
            </p>
          </div>
          <div>
            <h2>失敗時の制御</h2>
            <p>
              <code>needs_revision</code> は品質差し戻し、<code>failed</code> は実行失敗、<code>rejected</code> はスキーマ不正として分けます。
              自動再生成は連続回数を制限し、公開済み版には影響しない preview 側で止めます。
            </p>
            <p>
              無音停滞は Receptor が判定し、停止、待機、直前の成功段階からの再トライをユーザーに選ばせます。
            </p>
          </div>
        </section>

        <section className="detail-section detail-two-col">
          <div>
            <h2>3つの人間承認</h2>
            <div className="detail-gates">
              <div><b>受付承認</b><span>依頼内容を取り違えないための「お願い」。</span></div>
              <div><b>設計承認</b><span>実装前に「何を作るか」を確認する「これで作って」。</span></div>
              <div><b>公開承認</b><span>プレビュー確認後の「反映して」。本公開の最終ゲートです。</span></div>
            </div>
          </div>
          <div>
            <h2>止まった時の扱い</h2>
            <p>
              長い生成や検証で無音が続いた場合、Receptor が停滞を検知してユーザーに確認します。
              勝手に破棄せず、停止、もう少し待つ、直前の成功段階から再トライを選べます。
            </p>
            <p>
              生成やレビューに失敗しても公開済み版は触りません。失敗はプレビュー側で止まり、必要な指摘とともに戻ります。
            </p>
          </div>
        </section>

        <section className="detail-section">
          <h2>Reviewer / Tester の判定観点</h2>
          <div className="detail-grid">
            <div><b>Sandbox</b><span>生成 HTML が外部通信、cookie、localStorage、別ウィンドウに依存しないこと。</span></div>
            <div><b>Persistence</b><span>状態を持つアプリが <code>AF.load()</code> / <code>AF.save()</code> にバインドされ、画面遷移後も復元すること。</span></div>
            <div><b>Worker operability</b><span>主要操作が <code>commands</code> または <code>state_schema</code> で表現され、自然言語指示から到達できること。</span></div>
            <div><b>UX fidelity</b><span>ユーザー要求をフォームだけで代替せず、実際に使える UI とレスポンシブ性を満たすこと。</span></div>
            <div><b>Boundary</b><span>生成 HTML 内にチャット UI を作らず、アプリ表示エリアと下部アプリチャットを分離すること。</span></div>
            <div><b>Deletion safety</b><span>削除は状態を残さず完全削除し、監査ログを残すこと。</span></div>
            <div><b>Model tier</b><span>軽い判断は FLASH、コード生成は PRO として、環境ごとに同等能力帯へマッピングすること。</span></div>
            <div><b>Preview safety</b><span>未通過の生成物、stub、検証 NG の成果物は active 化せず、ユーザー承認まで pending に留めること。</span></div>
          </div>
        </section>
      </main>
    </div>
  );
}

function ArchitectureDetailPage({
  user,
  showGuestCta,
  onSignIn,
  onGuestLogin,
  onOpenApp,
  onSignOut,
}: {
  user: User | null;
  showGuestCta: boolean;
  onSignIn: () => void;
  onGuestLogin: () => void;
  onOpenApp: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="landing">
      <LandingNav user={user} showGuestCta={showGuestCta} onSignIn={onSignIn} onGuestLogin={onGuestLogin} onOpenApp={onOpenApp} onSignOut={onSignOut} />
      <main className="detail-page">
        <a className="detail-back" href="#home">トップへ戻る</a>
        <section className="detail-hero">
          <span>Architecture Detail</span>
          <h1>役割を分けたエージェント構造</h1>
          <p>
            AgentForge は、1つの AI に全権を渡す構造ではありません。Receptor、Orchestrator、Tester、Reviewer、
            Specialist Worker を分離し、Control Plane、Agent Harness、Sandbox、Version 管理で副作用を制御します。
            エージェントの判断力と、決定的な公開・保存・巻き戻し API を組み合わせる設計です。
          </p>
        </section>

        <section className="detail-section">
          <h2>構造フロー図</h2>
          <div className="detail-svg-frame"><VerticalArchitectureFlowSvg /></div>
          <div className="detail-arch-support">
            <div><b>Agent Harness</b><span>判断、進捗、成果物、検証結果を横断的に記録。</span></div>
            <div><b>Sandbox</b><span>ミニアプリを iframe と AF API に閉じ込める。</span></div>
            <div><b>Specialist Worker</b><span>公開後の各ミニアプリ内データだけを操作。</span></div>
          </div>
        </section>

        <section className="detail-section">
          <h2>レイヤー構造</h2>
          <div className="detail-layer-map" aria-label="AgentForge の詳細アーキテクチャ">
            <div>
              <h3>体験層</h3>
              <span>メインチャット</span>
              <span>ミニアプリ</span>
              <span>アプリチャット</span>
            </div>
            <div>
              <h3>ワーカー層</h3>
              <span>Receptor</span>
              <span>Orchestrator</span>
              <span>Tester / Reviewer</span>
              <span>Specialist Worker</span>
            </div>
            <div>
              <h3>制御層</h3>
              <span>Control Plane</span>
              <span>Agent Harness</span>
              <span>Worker Registry</span>
              <span>Approval / Version</span>
            </div>
            <div>
              <h3>実行層</h3>
              <span>Sandbox iframe</span>
              <span>AF.load / AF.save</span>
              <span>Firestore / Cloud Run</span>
              <span>Docker 検証環境</span>
            </div>
          </div>
        </section>

        <section className="detail-section">
          <h2>実装アーキテクチャの要点</h2>
          <div className="detail-grid">
            <div><b>Frontend shell</b><span>上部のミニアプリ表示 iframe と下部のアプリチャットを分離。生成 HTML はチャット UI を持ちません。</span></div>
            <div><b>AF runtime API</b><span><code>AF.load/save</code>、<code>AF.setChatContext</code>、<code>AF.setChatVisible</code> で保存と会話文脈を制御します。</span></div>
            <div><b>Backend services</b><span>Reception、Orchestrator、Control Plane、Generated App、Auth を分け、HTTP と service ロジックを分離します。</span></div>
            <div><b>Firestore state</b><span>会話、feature state、worker runs、pipeline runs、version metadata をプロジェクト/feature 単位で保持します。</span></div>
            <div><b>Cloud Run production</b><span>本番は Cloud Run + Gemini。管理画面、許可メール、ゲストモード、公開フラグを環境設定とDBで制御します。</span></div>
            <div><b>Local demo bridge</b><span>開発・デモは Docker エミュレータと claude CLI bridge を使い、モデル以外は本番相当で検証します。</span></div>
            <div><b>Worker registry</b><span>非常駐ワーカーの状態、待機理由、モデル、最終更新時刻を管理し、固着時は停止扱いで回収します。</span></div>
            <div><b>Tool Gateway</b><span>副作用操作は schema 検証された API 経由に限定し、ワーカーが権限を勝手に増やせないようにします。</span></div>
          </div>
        </section>

        <section className="detail-section">
          <h2>ワーカーの責任分界</h2>
          <div className="detail-responsibility">
            <div><b>Receptor</b><span>ユーザーと話す入口。曖昧な依頼の確認、進捗報告、停滞時の確認を担当します。</span></div>
            <div><b>Orchestrator</b><span>設計と実装の統括。アプリ画面、操作 API、専門ワーカー設定を作ります。</span></div>
            <div><b>Tester</b><span>本番相当環境で実際に動かし、主要操作と受け入れ条件を確認します。</span></div>
            <div><b>Reviewer</b><span>サンドボックス、保存、API、UI、命名などの規約に合っているかを判定します。</span></div>
            <div><b>Specialist Worker</b><span>公開済みミニアプリの中身を扱う担当者。担当外の構造変更はメインチャットへ取り次ぎます。</span></div>
          </div>
        </section>

        <section className="detail-section detail-two-col">
          <div>
            <h2>Agent Harness</h2>
            <p>
              Harness は、ワーカーの判断、進捗、成果物、検証結果、レビュー指摘、リトライを記録する土台です。
              ただし一般ユーザーには raw trace をそのまま見せず、短い進捗や承認前サマリーとして見せます。
            </p>
          </div>
          <div>
            <h2>Control Plane</h2>
            <p>
              Control Plane は、公開、巻き戻し、承認、バージョン管理、ワーカー状態を扱う決定的な制御層です。
              AI が直接本公開や権限変更を行わないように、強い副作用はここに閉じ込めます。
            </p>
          </div>
        </section>

        <section className="detail-section detail-two-col">
          <div>
            <h2>Specialist Worker の設計</h2>
            <p>
              生成された各ミニアプリには、原則として 1 つの Specialist Worker が付きます。
              Worker は担当アプリの <code>commands</code> と <code>state_schema</code> を読み、
              自然言語から追加、更新、削除、一括変更、メモ追記、異常値の確認へ変換します。
            </p>
            <p>
              複数画面や詳細画面では <code>AF.setChatContext()</code> により会話文脈を分割し、
              「どのタスク詳細を編集中か」のような状態を Worker 側の判断に渡します。
            </p>
          </div>
          <div>
            <h2>Commands と State の使い分け</h2>
            <p>
              お絵描きやゲームのように UI 操作が自然なものは <code>commands</code> 中心、
              タスク、予定、家計簿、メモのようなデータ中心アプリは <code>state</code> または <code>hybrid</code> を使います。
            </p>
            <p>
              これにより未知の新アプリでも、Worker が固定コマンド名の暗記に依存せず、schema に沿ってデータを編集できます。
            </p>
          </div>
        </section>

        <section className="detail-section">
          <h2>安全境界</h2>
          <div className="detail-grid">
            <div><b>サンドボックス</b><span>ミニアプリは iframe 内で動き、外部通信や localStorage に依存しません。</span></div>
            <div><b>データ分離</b><span>保存データはアプリ単位で分け、Specialist Worker は担当アプリ内だけを扱います。</span></div>
            <div><b>承認ゲート</b><span>設計、プレビュー、本公開を分離し、未確認の生成物を公開しません。</span></div>
            <div><b>版管理</b><span>公開ごとにスナップショットを保存し、巻き戻しは LLM 不使用で直前版へ戻します。</span></div>
          </div>
        </section>
      </main>
    </div>
  );
}

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guestEnabled, setGuestEnabled] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [publicReady, setPublicReady] = useState(false);
  const [route, setRoute] = useState(() => window.location.hash.replace(/^#/, ""));

  useEffect(() => onAuthChange((u) => { setUser(u); setAuthReady(true); }), []);

  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.replace(/^#/, ""));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    getPublicConfig()
      .then((c) => {
        setGuestEnabled(c.guest_access_enabled);
        setAuthRequired(c.auth_required);
      })
      .catch(() => setGuestEnabled(false))
      .finally(() => setPublicReady(true));
  }, []);

  if ((!authReady && isFirebaseConfigured()) || !publicReady) {
    return <div className="centered">読み込み中…</div>;
  }

  if (authRequired && !isFirebaseConfigured()) {
    return (
      <div className="centered">
        <h1>Firebase 設定が必要です</h1>
        <p className="muted">
          認証込みローカルデモでは、frontend/.env.local に Firebase Web app config を設定してください。
        </p>
      </div>
    );
  }

  const noAuthLocal = !isFirebaseConfigured() && !authRequired;
  const landingRoutes = new Set(["home", "beginner", "features", "flow", "architecture", "safety"]);
  const detailRoutes = new Set(["pipeline-detail", "architecture-detail"]);
  const isLandingRoute = landingRoutes.has(route);
  const isDetailRoute = detailRoutes.has(route);
  const showHome = isLandingRoute || (isFirebaseConfigured() && authReady && !user && !isDetailRoute) || (noAuthLocal && route !== "app" && !isDetailRoute);
  const openApp = () => {
    window.location.hash = "app";
    setRoute("app");
  };
  const signIn = () => {
    if (noAuthLocal) {
      openApp();
      return;
    }
    void signInWithGoogle().then(openApp).catch((e) => setError(String(e)));
  };
  const guestLogin = () => {
    if (noAuthLocal) {
      openApp();
      return;
    }
    signIn();
  };
  const signOut = () => {
    void signOutUser()
      .then(() => {
        window.location.hash = "home";
        setRoute("home");
      })
      .catch((e) => setError(String(e)));
  };

  if (showHome) {
    return (
      <LandingPage
        user={user}
        showGuestCta={guestEnabled || noAuthLocal}
        error={error}
        onSignIn={signIn}
        onGuestLogin={guestLogin}
        onOpenApp={openApp}
        onSignOut={signOut}
      />
    );
  }

  if (route === "pipeline-detail") {
    return (
      <PipelineDetailPage
        user={user}
        showGuestCta={guestEnabled || noAuthLocal}
        onSignIn={signIn}
        onGuestLogin={guestLogin}
        onOpenApp={openApp}
        onSignOut={signOut}
      />
    );
  }

  if (route === "architecture-detail") {
    return (
      <ArchitectureDetailPage
        user={user}
        showGuestCta={guestEnabled || noAuthLocal}
        onSignIn={signIn}
        onGuestLogin={guestLogin}
        onOpenApp={openApp}
        onSignOut={signOut}
      />
    );
  }

  return <AppShell user={user} onShowHome={() => { window.location.hash = "home"; setRoute("home"); }} />;
}
