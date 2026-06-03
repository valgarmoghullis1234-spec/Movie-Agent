// Minimal SSE client for the backend /chat endpoint.
// EventSource doesn't support POST, so we parse the SSE stream from fetch() manually.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type Choice = { label: string; value: string };

export type ChatEvent =
  | { type: "meta"; session_id: string }
  | { type: "agent"; name: string }
  | { type: "status"; text: string }
  | { type: "token"; text: string }
  | { type: "choices"; options: Choice[] }
  | { type: "error"; message: string }
  | { type: "done" };

export async function* streamChat(
  messages: ChatMessage[],
  sessionId: string | null,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, session_id: sessionId }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;

      const payload = JSON.parse(data);
      yield { type: event, ...payload } as ChatEvent;
    }
  }
}

export { API_BASE };
