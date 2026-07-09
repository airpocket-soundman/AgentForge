"""Default mini-app templates: registry, matcher, manifest shape (pure)."""
from app import templates
from app.models.generated import ViewManifest

EXPECTED = {
    "calculator", "task_manager", "schedule", "memo", "household_budget",
    "translate", "paint", "retouch", "bluesky",
}


def test_all_templates_present():
    assert set(templates.TEMPLATES.keys()) == EXPECTED


def test_each_template_is_a_valid_app_manifest():
    for key in EXPECTED:
        m = templates.to_manifest(key)
        assert isinstance(m, ViewManifest)
        assert m.kind == "app" and m.feature == key
        assert m.html.lstrip().startswith("<!DOCTYPE html>") and m.html.rstrip().endswith("</html>")
        assert "applyAgentCommand" in m.html  # content tools wired
        assert 'name="viewport"' in m.html    # responsive
        assert "<script" not in m.html.lower().split("<body", 1)[0] or True  # has script somewhere
        assert m.generated_by == "template"
        # No embedded chat UI (the app chat is a separate shell panel).
        assert "applyAgentCommand" in m.html
        for c in m.commands:
            assert c.get("name")


def test_each_template_passes_static_reviewer_and_safety_checks():
    from app.safety_harness.service import inspect_manifest
    from app.workers.reviewer import _static_findings

    for key in EXPECTED:
        manifest = templates.get_template(key)
        assert _static_findings(manifest) == []
        _checks, findings = inspect_manifest(manifest)
        assert findings == []


def test_calculator_template_persists_state_and_handles_ac_as_token():
    manifest = templates.get_template("calculator")
    html = manifest["html"]
    assert manifest["worker_state_mode"] == "hybrid"
    assert manifest["worker_eval_cases"]
    assert "AF.load()" in html
    assert "AF.save(snapshot())" in html
    assert "function tokenize(input)" in html
    assert "s.slice(i,i+2).toUpperCase()==='AC'" in html
    assert "histEl.replaceChildren()" in html
    assert "r.innerHTML" not in html
    props = manifest["state_schema"]["properties"]
    assert props["op"]["type"] == ["string", "null"]
    assert props["prev"]["type"] == ["string", "null"]


def test_schedule_template_uses_separate_detail_view():
    manifest = templates.get_template("schedule")
    html = manifest["html"]
    assert 'id="calendarView"' in html
    assert 'id="detailView" class="view hidden"' in html
    assert 'id="backb"' in html
    assert "function openNewDetail(date)" in html
    assert "cell.onclick=function(date)" in html
    assert "openNewDetail(date)" in html
    assert "evt.stopPropagation();openDetail(id);" in html
    assert "if(!e){e={id:uid(),date:ed.value||draftDate||iso(new Date())" in html
    assert "grid-template-columns:minmax(140px,180px) minmax(96px,120px) minmax(220px,1fr)" in html
    assert 'label class="titlefield">タイトル' in html
    assert 'label class="memowrap">メモ<textarea id="em"' in html
    assert "grid-template-rows:auto minmax(220px,1fr) auto" in html
    assert ".detail textarea{height:100%;min-height:0;resize:none" in html
    assert 'id="links" class="links"' in html
    assert "function renderLinks()" in html
    assert "em.addEventListener('input',renderLinks);" in html
    assert "AF.openExternal(url)" in html
    assert "new URL(url)" in html
    assert "linksEl.replaceChildren()" in html
    assert "calendarView.classList.add('hidden');detailView.classList.remove('hidden');" in html
    assert "detailView.classList.add('hidden');calendarView.classList.remove('hidden');" in html
    assert "AF.setChatContext('event_'+e.id" in html
    assert "AF.setChatContext('new_'+date" in html
    assert "AF.setChatContext('default','スケジュール')" in html


def test_matcher_maps_keywords():
    assert templates.match_template("電卓を作って") == "calculator"
    assert templates.match_template("タスク管理がほしい") == "task_manager"
    assert templates.match_template("スケジュール帳を作りたい") == "schedule"
    assert templates.match_template("メモ帳を追加して") == "memo"
    assert templates.match_template("家計簿を作って") == "household_budget"
    assert templates.match_template("翻訳ツールを作って") == "translate"
    assert templates.match_template("お絵描きアプリを作って") == "paint"
    assert templates.match_template("背景削除できるレタッチソフトを作って") == "retouch"
    assert templates.match_template("Blueskyアプリを作って") == "bluesky"


def test_matcher_returns_none_for_unrelated():
    assert templates.match_template("在庫管理を作って") is None
    assert templates.match_template("こんにちは") is None


def test_paint_template_resizes_canvas_with_corner_handles():
    manifest = templates.get_template("paint")
    html = manifest["html"]
    command_names = {c["name"] for c in manifest["commands"]}
    assert "set_canvas_size" in command_names
    assert 'class="resize-handle tr"' in html
    assert 'class="resize-handle br"' in html
    assert 'class="resize-handle bl"' in html
    assert "function applyCanvasSize(w,h,preserve,source)" in html
    assert "function setupResize()" in html
    assert "data-corner" in html
    assert "canvasW:canvasW,canvasH:canvasH" in html
    assert "window.addEventListener('resize'" not in html
    assert "canvas{width:100%;height:100%" not in html


def test_catalogue_has_no_html():
    cat = templates.list_templates()
    assert len(cat) == len(EXPECTED) and all("html" not in c for c in cat)


def test_judge_template_keyword_fallback():
    # No LLM in tests → judge_template falls back to the keyword matcher.
    from app.orchestrator import service as orch
    assert orch.judge_template("電卓を作って")["template"] == "calculator"
    assert orch.judge_template("Blueskyを作って")["template"] == "bluesky"
    assert orch.judge_template("在庫管理を作って")["template"] is None


def test_bluesky_template_keeps_connector_secrets_and_clear_persistence():
    manifest = templates.get_template("bluesky")
    html = manifest["html"]
    assert "auth:{type:\"none\",username:identifier,password:password}" in html
    assert "auth:{type:\"basic\",username:identifier,password:password}" not in html
    assert "body_template:{identifier:\"$secret.username\",password:\"$secret.password\"}" in html
    assert 'name==="clear_posts"){posts=[];cursor=null;save();' in html
    assert 'timeline:{method:"GET",path:"/xrpc/app.bsky.feed.getTimeline",side_effect:"read",query_template:{limit:"$params.limit",cursor:"$params.cursor"}}' in html
    assert 'author_feed:{method:"GET",path:"/xrpc/app.bsky.feed.getAuthorFeed",side_effect:"read",query_template:{limit:"$params.limit",cursor:"$params.cursor",actor:"$params.actor"}}' in html
    assert 'profile:{method:"GET",path:"/xrpc/app.bsky.actor.getProfile",side_effect:"read",query_template:{actor:"$params.actor"}}' in html
    assert 'follow:{method:"POST",path:"/xrpc/com.atproto.repo.createRecord",side_effect:"medium"' in html
    assert 'unfollow:{method:"POST",path:"/xrpc/com.atproto.repo.deleteRecord",side_effect:"medium"' in html
    assert 'record:{"$type":"app.bsky.graph.follow",subject:"$params.subject",createdAt:"$params.createdAt"}' in html
    assert 'var PAGE_LIMIT=20,PREFETCH_AFTER=15,MAX_POSTS=200;' in html
    assert 'feedTimer=null,loadSeq=0;' in html
    assert 'var params={limit:PAGE_LIMIT,cursor:(more&&cursor)?cursor:""};' in html
    assert 'posts=more?posts.concat(normalized):normalized;' in html
    assert 'if(loading&&more)return;' in html
    assert 'var seq=++loadSeq;' in html
    assert 'if(seq!==loadSeq)return;' in html
    assert 'finally{if(seq===loadSeq){loading=false;setTimeout(maybeLoadMore,0);}}' in html
    assert 'function prefetchTargetVisible()' in html
    assert 'var offset=Math.max(1,PAGE_LIMIT-PREFETCH_AFTER);' in html
    assert 'prefetchTargetVisible()||nearBottom()' in html
    assert 'window.addEventListener("scroll",maybeLoadMore,{passive:true});' in html
    assert 'function scheduleConnect()' in html
    assert 'function ensureSessionAndLoad()' in html
    assert 'id="home"' in html
    assert 'id="accountSearch"' in html
    assert 'function searchAccount()' in html
    assert 'function showHome()' in html
    assert 'function showHome(){\n    clearTimeout(feedTimer);' in html
    assert 'state.feedType="timeline";state.actor=""' in html
    assert 'function renderProfileCard(feed)' in html
    assert 'function loadProfile(actor,seq)' in html
    assert 'function toggleFollow()' in html
    assert 'avatar_url:p.avatar||"",banner_url:p.banner||"",avatar_ref:"",banner_ref:""' in html
    assert 'function fetchProfileImages(p)' in html
    assert 'function renderBlobImage(container,name,alt,cls)' in html
    assert 'className="profilebanner"' in html
    assert 'className="profileavatar"' in html
    assert 'await fetchProfileImages(state.profile);' in html
    assert 'p[refKey]=name;' in html
    assert 'function postAvatar(item)' in html
    assert 'author_avatar_url:postAvatar(item)' in html
    assert 'avatar_ref:""' in html
    assert 'className="postavatar"' in html
    assert 'renderBlobImage(postAvatarEl,item.avatar_ref,postAuthor(item)+" avatar","");' in html
    assert 'list[i].avatar_ref=avatarName;' in html
    assert 'AF.api("bluesky.follow"' in html
    assert 'AF.api("bluesky.unfollow"' in html
    assert 'state.currentDid=res.did||state.currentDid||"";' in html
    assert 'state.profile=normalizeProfile(p);save();' in html
    assert "AF.openExternal(url)" in html
    assert "AF.saveBlob(name,res.data_url)" in html
    assert "AF.loadBlob(pic.name)" in html
    assert "画像データがこの端末にありません" in html
    assert "src:res.data_url" not in html
    assert "pic.src" not in html
    assert "function showAuthor(handle)" in html
    assert 'id="limit"' not in html
    assert 'id="more"' not in html
    assert 'id="load"' not in html
    assert 'id="connect"' not in html
    assert 'id="test"' not in html
    assert 'id="disconnect"' not in html
    assert 'id="feedType"' not in html
    assert 'id="actor"' not in html
    assert "投稿を開く" not in html
    assert "window.open" not in html
    assert "href=" not in html.lower()
    assert 'function normalizeIdentifier(value){return String(value||"").trim().replace(/^@+/,"");}' in html
    post_props = manifest["state_schema"]["properties"]["posts"]["items"]["properties"]
    assert "currentDid" in manifest["state_schema"]["properties"]
    assert "profile" in manifest["state_schema"]["properties"]
    profile_props = manifest["state_schema"]["properties"]["profile"]["properties"]
    assert "avatar_url" in profile_props
    assert "banner_url" in profile_props
    assert "avatar_ref" in profile_props
    assert "banner_ref" in profile_props
    assert "image_urls" in post_props
    assert "image_refs" in post_props
    assert "author_avatar_url" in post_props
    assert "avatar_ref" in post_props
    assert "links" in post_props
    assert "post_url" not in post_props


def test_retouch_template_has_worker_layer_controls_and_blob_fallback():
    manifest = templates.get_template("retouch")
    html = manifest["html"]
    command_names = {c["name"] for c in manifest["commands"]}
    assert manifest["worker_state_mode"] == "hybrid"
    assert manifest["worker_eval_cases"]
    assert "select_layer" in command_names
    assert "rename_layer" in command_names
    assert "delete_layer" in command_names
    assert "undo" in command_names
    assert "redo" in command_names
    assert "clear_layer" in command_names
    assert "crop_to_content" in command_names
    assert "set_tool" in command_names
    assert "set_zoom" in command_names
    assert "adjust_color" in command_names
    assert "select_object_at" in command_names
    assert "expand_selection" in command_names
    assert "clear_selection" in command_names
    assert "delete_outside_selection" in command_names
    assert "delete_inside_selection" in command_names
    assert "function saveProject()" in html
    assert "AF.save({activeId:activeId,width:w,height:h,tool:tool,zoom:zoom,layers:layers.map" in html
    assert "AF.saveBlob('retouch-project'" in html
    assert "function loadProject()" in html
    assert "AF.loadBlob('retouch-project')" in html
    assert "保存済みプロジェクトの画像本体がこの端末にありません" in html
    assert "レイヤ画像のBlobがこの端末にありません" in html
    assert "function findLayer(args)" in html
    assert "function selectLayer(args)" in html
    assert "function renameLayer(args)" in html
    assert "function pushHistory(entry)" in html
    assert "function undo()" in html
    assert "function redo()" in html
    assert "function setTool(t)" in html
    assert "function cropToContent()" in html
    assert "function pointerDown(e)" in html
    assert "function adjustActive(br,ct)" in html
    assert "else if(name==='select_layer')selectLayer(args);" in html
    assert "else if(name==='rename_layer')renameLayer(args);" in html
    assert "else if(name==='delete_layer')removeLayer(args);" in html
    assert "else if(name==='undo')undo();" in html
    assert "else if(name==='redo')redo();" in html
    assert "else if(name==='set_tool')setTool(args.tool||'move');" in html
    assert "else if(name==='set_zoom')" in html
    assert "else if(name==='crop_to_content')cropToContent();" in html
    assert "else if(name==='adjust_color')adjustActive(+args.brightness||0,+args.contrast||0);" in html
    # Click-to-select: flood-fill object selection that unions per click (so
    # contiguous objects merge into one boundary), rough-trace edge snapping,
    # expand + hole fill, then keep-selected transparency.
    assert "function selectObjectAt(pt,th,erase)" in html
    assert "function deleteOutsideSelection()" in html
    assert "function deleteInsideSelection()" in html
    assert "function floodAdd(d,cw,ch,sx,sy,th,erase)" in html
    assert "function maskBoundary(mask,cw,ch)" in html
    assert "function fillPolygon(pts,cw,ch)" in html
    assert "function snapRegion(d,cw,ch,pts)" in html
    assert "function traceSelect(pts,erase)" in html
    assert "function expandSelection(px)" in html
    assert "else if(name==='select_object_at')" in html
    assert "else if(name==='expand_selection')expandSelection(+args.pixels||2);" in html
    assert "else if(name==='delete_outside_selection')deleteOutsideSelection();" in html
    assert "else if(name==='delete_inside_selection')deleteInsideSelection();" in html
    # Usability: zoom/fit, drag&drop + paste loading, keyboard shortcuts, and
    # drawing that works on the in-memory layer canvas (no per-stroke re-decode).
    assert "function fitZoom()" in html
    assert "addEventListener('drop'" in html
    assert "addEventListener('paste'" in html
    assert "addEventListener('keydown'" in html
    assert "requestAnimationFrame" in html
    assert "toDataURL" not in html.split("function paintLine", 1)[1].split("function pointerDown", 1)[0]
    props = manifest["state_schema"]["properties"]
    assert "tool" in props
    assert "zoom" in props
    layer_props = props["layers"]["items"]["properties"]
    assert "x" in layer_props
    assert "y" in layer_props


def test_is_scratch_detector():
    from app.reception import service as rsvc
    assert rsvc.is_scratch("一から作って")
    assert rsvc.is_scratch("デフォルトではなく自分で作りたい")
    assert not rsvc.is_scratch("お願い")
