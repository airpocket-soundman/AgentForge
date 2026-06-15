"""Reception module — Phase 1 + conversational control.

Responsibilities:
- Accept a chat message from the Web Shell over REST and persist it to Firestore.
- Route by intent:
    build_feature:* -> Orchestrator (generate plan + register pending)
    approve         -> Control Plane: approve the latest pending plan ("反映して")
    rollback        -> Control Plane: soft-disable active features ("戻して")
    chat            -> templated reply
- Reply immediately; the browser also subscribes to Firestore for live state.
"""
from fastapi import APIRouter

from app.control_plane import approvals, registry, worker_status
from app.models.reception import ChatMessage, MessageIn, ReceptionReply
from app.reception import service

router = APIRouter(prefix="/api/reception", tags=["reception"])


@router.get("/health")
def reception_health() -> dict:
    return {"status": "ok", "module": "reception"}


@router.get("/state/{project_id}")
def get_state(project_id: str) -> dict:
    """Full chat state for the browser to render from scratch and poll while a
    background design runs (survives navigation / reload).

    The poll doubles as the Receptor's stall watch (VISION 柱5): while a build is
    running it judges slow/stuck and PROACTIVELY posts the ①②③ choices — the user
    doesn't have to speak first. Poll-driven ⇒ pauses while the app is closed."""
    try:
        service.judge_stall_on_poll(project_id)
    except Exception:  # noqa: BLE001 — the watch must never break state reads
        pass
    return service.conversation_state(project_id)


@router.get("/candidate/{project_id}")
def get_candidate(project_id: str) -> dict:
    """The generated app awaiting publish (new or edited), for the chat preview."""
    return {"manifest": service.get_candidate(project_id)}


@router.post("/messages", response_model=ReceptionReply)
def post_message(body: MessageIn) -> ReceptionReply:
    conversation_id = service.conversation_id_for(body.project_id)
    # Receptor is active while handling a message (returns to idle below).
    worker_status.record_status("Receptor", body.project_id, worker_status.ACTIVE, model=service._model_for_phase("planning"))
    service.append_message(conversation_id, ChatMessage(role="user", text=body.text))

    # The main worker is busy: the reception worker actually INVESTIGATES the
    # pipeline (diagnose_build) instead of replying from a template, and can
    # release a chat that a dead worker left locked.
    build = service.current_build(body.project_id)
    if build.get("status") == "designing":
        diag = service.diagnose_build(body.project_id)

        def _busy_reply(text: str, intent: str, building: bool) -> ReceptionReply:
            r = ChatMessage(role="assistant", text=text)
            service.append_message(conversation_id, r)
            worker_status.record_status("Receptor", body.project_id, worker_status.IDLE)
            return ReceptionReply(conversation_id=conversation_id, reply=r, detected_intent=intent, building=building)

        # ① 停止 (escape hatch — busy-guard otherwise blocks every message)
        if service.is_cancel(body.text):
            service.recover_build(body.project_id, "user cancelled")
            service.clear_flow(body.project_id)
            return _busy_reply("作業を中止しました。新しいご依頼をどうぞ。", "cancel", False)
        # ③ 停止して再トライ (resume from the last good stage)
        if service.is_retry(body.text):
            service.retry_build(body.project_id)
            return _busy_reply("停止して、直前の成功段階から再トライします。進捗はこの画面に表示されます。", "retry", True)
        # ② もう少し待つ — restart the stall clock so the watch doesn't immediately
        # re-judge the same run (next timeout will be #2 = force stop).
        if service.is_wait(body.text):
            service.extend_wait(body.project_id)
            return _busy_reply(f"承知しました。このままお待ちください（経過 {diag.get('total_sec', 0)} 秒・生成中）。", "waiting", True)

        # Receptor judges timeout (slow/stuck). The poll-driven watch usually prompts
        # first (proactively); if a prompt is already pending, just remind the choices.
        if diag["health"] in ("slow", "stuck"):
            if build.get("prompt_pending"):
                return _busy_reply(
                    "①「停止」／ ②「もう少し待つ」／ ③「停止して再トライ」からお選びください。",
                    "timeout_prompt", True,
                )
            count = service.bump_timeout(body.project_id)
            if count >= service._TIMEOUT_FORCE_STOP_N:
                service.recover_build(body.project_id, f"force-stop after {count} timeouts")
                return _busy_reply(service._force_stop_text(count, diag), "force_stopped", False)
            service.mark_prompted(body.project_id)
            return _busy_reply(service._timeout_prompt_text(diag), "timeout_prompt", True)

        # progressing → normal, grounded status reply
        return _busy_reply(service.building_status_reply(body.project_id, body.text, diag), "busy", True)

    # Attachments: text/data files are inlined into the request; images go to the
    # LLM for vision. Intent/feature resolution still keys off the typed text only.
    extra_text, images = service.split_attachments(body.attachments)
    goal_text = body.text + extra_text

    # Status query (いまどうなってる？/状況/進捗/報告して …) — answer at ANY stage via
    # the pipeline-status API, BEFORE the stage branches so it isn't swallowed as a
    # confirm-revision / build request. (During a build the busy block above already
    # answered with the grounded status.)
    if service.is_status_query(body.text):
        r = ChatMessage(role="assistant", text=service.pipeline_status_reply(body.project_id, body.text))
        service.append_message(conversation_id, r)
        worker_status.record_status("Receptor", body.project_id, worker_status.IDLE)
        return ReceptionReply(conversation_id=conversation_id, reply=r, detected_intent="status",
                              task_id=None, approval_id=None, activated_feature=None,
                              disabled_feature=None, building=False)

    flow = service.get_flow(body.project_id)
    stage = flow.get("stage", "idle")
    intent = service.classify(body.text)
    task_id: str | None = None
    approval_id: str | None = None
    activated_feature: str | None = None
    disabled_feature: str | None = None
    building = False
    dispatched_bg = False  # set when the substantive request is handed to the bg worker

    # === Worker chat (app chat) on/off — a deterministic feature-level toggle ===
    # Handle it directly (Receptor, light): no Orchestrator / no codegen. Works
    # from idle or while a restatement is pending (a new command supersedes it).
    worker_toggle = service.worker_toggle_intent(body.text)
    if worker_toggle is not None and stage in ("idle", "confirm"):
        if stage == "confirm":
            service.clear_flow(body.project_id)
        feat = service.resolve_feature(body.project_id, body.text) or registry.get_last_changed(body.project_id)
        if not feat:
            reply_text = "どの機能のワーカーチャットか分かりませんでした。対象の機能名を添えて、もう一度お願いします。"
        else:
            approvals.set_worker(body.project_id, feat, worker_toggle)
            title = service.feature_title(body.project_id, feat)
            if worker_toggle:
                reply_text = f"「{title}」のアプリチャット（ワーカーチャット）を表示にしました。"
            else:
                reply_text = (
                    f"「{title}」のアプリチャット（ワーカーチャット）を非表示にしました。\n"
                    "※ ワーカーチャットは機能単位の設定です。『一覧画面だけ非表示』のように画面ごとに分けることはできません。"
                )

    # === Stage: Receptor restated the request, awaiting user's OK to dispatch ==
    elif stage == "confirm":
        if service.is_cancel(body.text):
            service.clear_flow(body.project_id)
            reply_text = "承知しました。依頼を取りやめました。新しいご依頼をどうぞ。"
        elif service.is_plan_ok(body.text):
            allowed, count = service.guard_run(body.project_id)
            if not allowed:
                reply_text = (
                    f"短時間に実行が集中しています（直近{count}回）。少し待ってから「お願い」と送ってください。"
                )
            else:
                res = service.dispatch_confirmed(body.project_id)
                building = True
                reply_text = (
                    "承知しました。制作チーム（Orchestrator）に依頼しました。"
                    "進捗はこの画面に表示されます。"
                )
        else:
            # Anything else = a correction; re-consolidate and re-confirm.
            service.start_confirm_bg(
                body.project_id, flow.get("mode", "create"), flow.get("feature"),
                (flow.get("goal") or "") + "\n\n[ユーザーの修正・追記] " + goal_text,
            )
            reply_text = "承知しました。内容を更新して、もう一度確認します…"

    # === Stage: a design PROPOSAL is under review =========================
    elif stage == "plan":
        if service.is_cancel(body.text):
            service.clear_flow(body.project_id)
            reply_text = "設計をキャンセルしました。新しく機能を依頼してください。"
        elif service.is_plan_ok(body.text):
            allowed, count = service.guard_run(body.project_id)
            if not allowed:
                reply_text = (
                    f"短時間に実行が集中しています（直近{count}回）。トークン保護のため一時停止しました。"
                    "少し待ってから「これで作って」と送ってください。"
                )
            else:
                service.start_codegen(body.project_id, flow["goal"], flow["plan"])
                building = True
                reply_text = (
                    "プランを承認しました。AIワーカーがコードを生成します。\n"
                    "完了するとここにプレビューが表示されます。"
                )
        else:
            # Anything else = a revision instruction; rebuild the proposal.
            service.start_plan(
                body.project_id, flow["goal"], feedback=goal_text, previous=flow["plan"], images=images
            )
            building = True
            reply_text = "修正を反映して設計案を作り直します。"

    # === Stage: code is BUILT, awaiting publish ===========================
    elif stage == "built":
        if intent == "approve" or service.is_plan_ok(body.text):
            if flow.get("mode") == "edit":
                title = (flow.get("candidate") or {}).get("title") or service.feature_label(flow["feature"])
                res = approvals.publish_edit(body.project_id, flow["feature"], flow["candidate"])
                activated_feature = res["feature"]
                # Ledger: the published edit instruction becomes a pinned requirement.
                registry.append_requirements(body.project_id, activated_feature, [flow.get("goal") or ""])
                service.clear_flow(body.project_id)
                reply_text = f"「{title}」を更新しました。"
            else:
                approval_id = flow.get("approval_id")
                if not approval_id:
                    # No approval was registered for this candidate (e.g. an
                    # errored/partial codegen) — don't call approve(None).
                    service.clear_flow(body.project_id)
                    reply_text = "公開対象が見つかりませんでした。お手数ですが、もう一度ご依頼ください。"
                else:
                    res = approvals.approve(approval_id)
                    activated_feature = res["feature"]
                    # Ledger: the build goal + approved acceptance criteria become
                    # pinned requirements future edits must keep holding.
                    registry.append_requirements(
                        body.project_id, activated_feature,
                        [flow.get("goal") or ""] + list((flow.get("plan") or {}).get("acceptance") or []),
                    )
                    service.clear_flow(body.project_id)
                    reply_text = f"公開しました。「{service.feature_title(body.project_id, activated_feature)}」を左メニューに追加しました。"
        elif service.is_cancel(body.text) or intent == "rollback":
            service.clear_flow(body.project_id)
            reply_text = "キャンセルしました（生成物は破棄しました）。"
        else:
            # A substantive message at the preview = a revision to the CANDIDATE:
            # regenerate → gate → re-preview. The user can iterate BEFORE publishing
            # (previously the only options were 反映して / キャンセル).
            allowed, count = service.guard_run(body.project_id)
            if not allowed:
                reply_text = (
                    f"短時間に実行が集中しています（直近{count}回）。少し待ってからもう一度指示してください。"
                )
            else:
                service.start_candidate_revision(body.project_id, goal_text, images=images)
                building = True
                reply_text = "プレビューに修正を加えます。完了したら更新版を表示します（公開はまだされません）。"

    # === Stage: idle ======================================================
    elif intent == "approve":
        pending = approvals.find_latest_pending(body.project_id)
        if pending:
            res = approvals.approve(pending["approval_id"])
            activated_feature = res["feature"]
            approval_id = pending["approval_id"]
            reply_text = f"承認しました。「{service.feature_label(activated_feature)}」を有効化しました。"
        else:
            reply_text = "承認できる設計がありません。先に作りたい機能を伝えてください。"

    elif intent == "rollback":
        # 巻き戻し: undo the most recent change by restoring the previous version
        # (linear, no branching). Targets the last-changed feature.
        feature = registry.get_last_changed(body.project_id)
        if not feature:
            reply_text = "戻せる変更がありません。"
        else:
            res = approvals.rollback_feature(body.project_id, feature)
            title = service.feature_title(body.project_id, feature)
            if res.get("status") == "disabled":
                disabled_feature = feature
                reply_text = f"「{title}」を巻き戻しました（作成前に戻し、無効化）。"
            else:
                disabled_feature = None
                reply_text = f"「{title}」を直前の版に巻き戻しました。"

    else:
        # Substantive request. Classification calls an LLM, so run it (and the
        # routing) in the background and acknowledge IMMEDIATELY — the Receptor does
        # only light work synchronously. The background then posts progress/results
        # (build) or a conversational reply (chat).
        service.handle_request_bg(body.project_id, goal_text, images=images)
        building = True
        dispatched_bg = True
        reply_text = "受け付けました。内容を確認して進めます。"

    assistant_msg = ChatMessage(role="assistant", text=reply_text)
    service.append_message(conversation_id, assistant_msg)
    # Don't flip Receptor to idle here when we handed off to the background worker:
    # that worker now OWNS the Receptor status (active while 整理中 → idle at confirm),
    # and racing it back to idle would hide the work in the monitor.
    if not dispatched_bg:
        worker_status.record_status("Receptor", body.project_id, worker_status.IDLE)

    return ReceptionReply(
        conversation_id=conversation_id,
        reply=assistant_msg,
        detected_intent=intent,
        task_id=task_id,
        approval_id=approval_id,
        activated_feature=activated_feature,
        disabled_feature=disabled_feature,
        building=building,
    )
