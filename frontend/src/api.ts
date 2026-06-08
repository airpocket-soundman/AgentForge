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
    throw new Error(detail);
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
