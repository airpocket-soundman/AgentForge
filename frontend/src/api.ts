// Thin client for the AgentForge core API. Calls go through Vite's /api proxy
// in dev; in production the SPA (Firebase Hosting) rewrites /api to Cloud Run.
import { getIdToken } from "./firebase";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  text: string;
  created_at: string;
}

export interface ReceptionReply {
  conversation_id: string;
  reply: ChatMessage;
  detected_intent: string | null;
}

export async function sendMessage(
  text: string,
  projectId = "default",
): Promise<ReceptionReply> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = await getIdToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch("/api/reception/messages", {
    method: "POST",
    headers,
    body: JSON.stringify({ text, project_id: projectId }),
  });
  if (!res.ok) {
    throw new Error(`Reception API error: ${res.status}`);
  }
  return res.json();
}
