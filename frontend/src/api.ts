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
  created_at: string;
}

export interface ReceptionReply {
  conversation_id: string;
  reply: ChatMessage;
  detected_intent: string | null;
  task_id: string | null;
  approval_id: string | null;
  activated_feature: string | null;
  disabled_feature: string | null;
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

export function sendMessage(text: string, projectId = PROJECT_ID): Promise<ReceptionReply> {
  return request<ReceptionReply>("/api/reception/messages", {
    method: "POST",
    body: JSON.stringify({ text, project_id: projectId }),
  });
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

// --- Feature-level managing AI worker (standard: instruction area per feature) ---

export function getFeatureWorker(
  feature: string,
  projectId = PROJECT_ID,
): Promise<{ enabled: boolean; messages: ChatMessage[] }> {
  return request(`/api/app/features/${feature}/worker?project_id=${encodeURIComponent(projectId)}`);
}

export function sendFeatureWorkerMessage(
  feature: string,
  text: string,
  projectId = PROJECT_ID,
): Promise<{ reply: ChatMessage; created: { task_id: string; title: string }[] }> {
  return request(`/api/app/features/${feature}/worker/messages`, {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, text }),
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
  theme: string;
  fields: FieldSpec[];
  list_columns: string[];
  stats?: StatSpec[];
  charts?: ChartSpec[];
  gantt?: GanttSpec | null;
  calendar?: CalendarSpec | null;
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
