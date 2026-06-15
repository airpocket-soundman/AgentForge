// Thin client for the AgentForge core API. Calls go through Vite's /api proxy
// in dev; in production the SPA (Firebase Hosting) rewrites /api to Cloud Run.
import { getIdToken } from "./firebase";

export const PROJECT_ID = "default";

// When VITE_API_BASE is set (e.g. the Cloud Run URL), call the deployed API
// directly (real Gemini / real Firestore). Otherwise use relative paths that the
// Vite dev proxy forwards to the local backend.
const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

function url(path: string): string {
  return `${API_BASE}${path}`;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  text: string;
  // Optional inline SVG image (plan-stage screen mock) — rendered as <img>.
  svg?: string | null;
  created_at: string;
}

// A file/image attached to a chat message. text: file content; image: base64.
export interface Attachment {
  name: string;
  mime: string;
  kind: "image" | "text";
  content: string;
}

export interface ReceptionReply {
  conversation_id: string;
  reply: ChatMessage;
  detected_intent: string | null;
  task_id: string | null;
  approval_id: string | null;
  activated_feature: string | null;
  disabled_feature: string | null;
  building: boolean;
}

// Full chat state the browser renders from scratch and polls while a background
// design runs (so navigating away / reloading keeps the design going).
export interface ConversationState {
  conversation_id: string;
  messages: ChatMessage[];
  building: boolean;
  // What the worker is doing now while building: "planning" | "revising" | "codegen" | "editing".
  phase?: string | null;
  // Flow: "idle" | "confirm" (restated, awaiting OK) | "plan" | "built".
  stage: "idle" | "confirm" | "plan" | "built";
  mode: "create" | "edit"; // at "built": new feature vs editing an existing one
  pending_feature: string | null; // at "built": the feature to preview
  pending_approval_id: string | null; // at "built": the approval to publish
}

export interface Task {
  task_id: string;
  project_id: string;
  title: string;
  done: boolean;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  const token = await getIdToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url(path), { ...init, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return res.json() as Promise<T>;
}

export function sendMessage(
  text: string,
  attachments: Attachment[] = [],
  projectId = PROJECT_ID,
): Promise<ReceptionReply> {
  return request<ReceptionReply>("/api/reception/messages", {
    method: "POST",
    body: JSON.stringify({ text, project_id: projectId, attachments }),
  });
}

export function getConversationState(projectId = PROJECT_ID): Promise<ConversationState> {
  return request<ConversationState>(`/api/reception/state/${encodeURIComponent(projectId)}`);
}

export function approve(approvalId: string): Promise<{ status: string; feature: string }> {
  // Empty-body POST: browsers set Content-Length: 0 automatically (Cloud Run GFE
  // requires it). We send "{}" to be safe across clients.
  return request(`/api/control-plane/approvals/${approvalId}/approve`, {
    method: "POST",
    body: "{}",
  });
}

export function listTasks(projectId = PROJECT_ID): Promise<{ tasks: Task[] }> {
  return request<{ tasks: Task[] }>(`/api/app/tasks?project_id=${encodeURIComponent(projectId)}`);
}

export function createTask(title: string, dueDate?: string, projectId = PROJECT_ID): Promise<Task> {
  return request<Task>("/api/app/tasks", {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, title, due_date: dueDate ?? null }),
  });
}

export function setTaskDone(taskId: string, done: boolean): Promise<Task> {
  return request<Task>(`/api/app/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify({ done }),
  });
}

export interface TaskDetail extends Task {
  messages: ChatMessage[];
  summary: string;
}

export function getTask(taskId: string): Promise<TaskDetail> {
  return request<TaskDetail>(`/api/app/tasks/${taskId}`);
}

export function sendTaskMessage(
  taskId: string,
  text: string,
): Promise<{ reply: ChatMessage; summary: string }> {
  return request(`/api/app/tasks/${taskId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function getFeatureStates(projectId = PROJECT_ID): Promise<Record<string, string>> {
  return request<Record<string, string>>(`/api/control-plane/features/${encodeURIComponent(projectId)}`);
}

export function disableFeature(feature: string, projectId = PROJECT_ID): Promise<{ status: string }> {
  return request(`/api/control-plane/features/${encodeURIComponent(projectId)}/${feature}/disable`, {
    method: "POST",
    body: "{}",
  });
}

// DEV ONLY: wipe all data and return to the initial state.
export function resetAll(): Promise<{ status: string; deleted: Record<string, number> }> {
  return request("/api/control-plane/reset", { method: "POST", body: "{}" });
}

// --- Status monitor: running background workers + global stop ---

export interface RunningWorker {
  conversation_id: string;
  project_id: string;
  phase: string | null;
  goal: string;
  total_sec: number;
  health: "progressing" | "slow" | "stuck" | string;
}

export interface WorkerUsage {
  runs_in_window: number;
  max_runs: number;
  window_sec: number;
  total_runs: number;
  total_blocked: number;
}

// Worker registry entry (status monitor): one row per worker type/project.
export interface WorkerRegistryEntry {
  worker_type: string;
  project_id: string;
  status: "active" | "idle" | "stopped" | string;
  stale: boolean;
  detail: string | null;
  model: string | null;
  task_id: string | null;
  since_update_sec: number;
}

export function getWorkers(
  projectId = PROJECT_ID,
): Promise<{ registry: WorkerRegistryEntry[]; workers: RunningWorker[]; usage: WorkerUsage }> {
  return request(`/api/control-plane/workers?project_id=${encodeURIComponent(projectId)}`);
}

// Change history (audit timeline) — who/what/when/why.
export interface HistoryEntry {
  log_id: string;
  action: string;
  target: string;
  project_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export function getHistory(projectId = PROJECT_ID, limit = 100): Promise<{ history: HistoryEntry[] }> {
  return request(`/api/control-plane/history/${encodeURIComponent(projectId)}?limit=${limit}`);
}

// Published version stack for a feature (rollback targets).
export interface VersionMeta {
  seq: number;
  action: string;
  created_at: string;
  title: string | null;
}

export function getVersions(feature: string, projectId = PROJECT_ID): Promise<{ versions: VersionMeta[] }> {
  return request(`/api/control-plane/versions/${encodeURIComponent(projectId)}/${encodeURIComponent(feature)}`);
}

// --- Pipeline run log (developer view) ---

export interface PipelineRun {
  task_id: string;
  project_id: string | null;
  goal: string | null;
  intent: string | null;
  first_ts: string | null;
  last_ts: string | null;
  events: number;
  last_status: string | null;
  running?: boolean;
}

export function getRuns(projectId = PROJECT_ID, limit = 20): Promise<{ runs: PipelineRun[] }> {
  return request(`/api/control-plane/runs?project_id=${encodeURIComponent(projectId)}&limit=${limit}`);
}

export interface RunMessage {
  kind: "request" | "report" | "event" | string;
  ts?: string;
  from?: string;
  to?: string;
  intent?: string;
  status?: string;
  event?: string;
  text?: string;
  error?: string | null;
  findings?: string[];
}

export function getRunThread(taskId: string): Promise<{ messages: RunMessage[] }> {
  return request(`/api/control-plane/messages/${encodeURIComponent(taskId)}`);
}

// Stop ALL running background workers across sessions (release every locked chat).
export function stopAllWorkers(): Promise<{ stopped: number; conversations: string[] }> {
  return request("/api/control-plane/stop-all", { method: "POST", body: "{}" });
}

// --- Feature-level managing AI worker (standard: instruction area per feature) ---
// A GENERAL chat with the feature's own worker: it answers conversationally and,
// when asked to change the feature, forwards the request into the SAME app-design
// pipeline the main chat uses (the Orchestrator decides create-vs-edit). The
// resulting preview + 反映 surface from the shared conversation state
// (getConversationState / getCandidate / sendMessage("反映して")).

export interface FeatureWorkerState {
  enabled: boolean;
  messages: ChatMessage[];
}

export function getFeatureWorker(
  feature: string,
  projectId = PROJECT_ID,
): Promise<FeatureWorkerState> {
  return request(`/api/app/features/${encodeURIComponent(feature)}/worker?project_id=${encodeURIComponent(projectId)}`);
}

export function sendFeatureWorkerMessage(
  feature: string,
  text: string,
  attachments: Attachment[] = [],
  projectId = PROJECT_ID,
): Promise<{
  reply: ChatMessage;
  building: boolean;
  created: { task_id: string; title: string }[];
  data_changed?: boolean;
  command?: { name: string; arguments?: Record<string, unknown> } | null; // MCP-style tool call
}> {
  return request(`/api/app/features/${encodeURIComponent(feature)}/worker/messages`, {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, text, attachments }),
  });
}

export function setFeatureWorker(
  feature: string,
  enabled: boolean,
  projectId = PROJECT_ID,
): Promise<{ worker_enabled: boolean }> {
  return request(`/api/control-plane/features/${encodeURIComponent(projectId)}/${feature}/worker`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

// --- Identity, feature flags, and admin (separate admin allowlist) ---

export interface FeatureFlags {
  byok_visible: boolean;
}

export interface Me {
  uid: string;
  email: string;
  is_admin: boolean;
  feature_flags: FeatureFlags;
}

export function getMe(): Promise<Me> {
  return request<Me>("/api/me");
}

export interface AdminConfig {
  allowlist_editable: string[];
  allowlist_effective: string[];
  admin_emails: string[];
  feature_flags: FeatureFlags;
}

export function getAdminConfig(): Promise<AdminConfig> {
  return request<AdminConfig>("/api/admin/config");
}

export function setAllowlist(emails: string[]): Promise<{ emails: string[] }> {
  return request("/api/admin/allowlist", { method: "POST", body: JSON.stringify({ emails }) });
}

export function setFeatureFlags(flags: Partial<FeatureFlags>): Promise<FeatureFlags> {
  return request<FeatureFlags>("/api/admin/feature-flags", {
    method: "POST",
    body: JSON.stringify(flags),
  });
}

// --- AI-generated features: view manifest + generic entity CRUD (real self-expansion) ---

export interface FieldSpec {
  key: string;
  label: string;
  type: "text" | "textarea" | "number" | "date" | "checkbox" | "markdown";
}

export interface ChartSpec {
  type: "bar" | "line" | "pie" | "doughnut";
  title: string;
  category: string; // field key for labels
  value: string;    // numeric field key
}

export interface StatSpec {
  label: string;
  value: string;
  agg: "sum" | "count" | "avg";
}

export interface GanttSpec {
  label: string;
  start: string;
  end: string;
}

export interface CalendarSpec {
  date: string;
  title: string;
}

export interface ViewManifest {
  feature: string;
  title: string;
  description?: string;
  kind?: "data" | "app";
  theme: string;
  fields: FieldSpec[];
  list_columns: string[];
  stats?: StatSpec[];
  charts?: ChartSpec[];
  gantt?: GanttSpec | null;
  calendar?: CalendarSpec | null;
  html?: string;
  // MCP-style tool definitions the mini-app exposes for its specialist worker.
  commands?: { name: string; description?: string; inputSchema?: Record<string, unknown> }[];
  generated_by: string;
}

export interface Entity {
  entity_id: string;
  feature: string;
  project_id: string;
  data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export function getView(feature: string, projectId = PROJECT_ID): Promise<ViewManifest> {
  return request<ViewManifest>(
    `/api/app/view/${encodeURIComponent(feature)}?project_id=${encodeURIComponent(projectId)}`,
  );
}

// Manifest regardless of approval status — used to preview generated code before publishing.
export function getPreview(feature: string, projectId = PROJECT_ID): Promise<ViewManifest> {
  return request<ViewManifest>(
    `/api/app/preview/${encodeURIComponent(feature)}?project_id=${encodeURIComponent(projectId)}`,
  );
}

// The app awaiting publish (new or edited) — preview source for the chat (works
// for edits too, where the live manifest is still the old one).
export async function getCandidate(projectId = PROJECT_ID): Promise<ViewManifest | null> {
  const r = await request<{ manifest: ViewManifest | null }>(
    `/api/reception/candidate/${encodeURIComponent(projectId)}`,
  );
  return r.manifest ?? null;
}

export function listEntities(feature: string, projectId = PROJECT_ID): Promise<{ items: Entity[] }> {
  return request<{ items: Entity[] }>(
    `/api/app/entities?feature=${encodeURIComponent(feature)}&project_id=${encodeURIComponent(projectId)}`,
  );
}

export function createEntity(
  feature: string,
  data: Record<string, unknown>,
  projectId = PROJECT_ID,
): Promise<Entity> {
  return request<Entity>("/api/app/entities", {
    method: "POST",
    body: JSON.stringify({ feature, project_id: projectId, data }),
  });
}

export function deleteEntity(entityId: string): Promise<{ deleted: string }> {
  return request(`/api/app/entities/${entityId}`, { method: "DELETE" });
}

// --- Whole-app persisted state for sandboxed generated apps (AF.load/AF.save) ---

export async function getAppState(feature: string, projectId = PROJECT_ID): Promise<unknown> {
  const r = await request<{ state: unknown }>(
    `/api/app/state/${encodeURIComponent(feature)}?project_id=${encodeURIComponent(projectId)}`,
  );
  return r.state ?? null;
}

export function setAppState(
  feature: string,
  state: unknown,
  projectId = PROJECT_ID,
): Promise<{ ok: boolean }> {
  return request(`/api/app/state/${encodeURIComponent(feature)}`, {
    method: "PUT",
    body: JSON.stringify({ project_id: projectId, state }),
  });
}
