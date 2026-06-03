"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat, type ChatMessage, type Choice } from "@/lib/chat";

type Msg = ChatMessage & { agent?: string; choices?: Choice[] };

const SUGGESTIONS = [
  "What's the plot of Inception?",
  "Reviews for Dune: Part Two",
  "Recommend me a movie",
  "Compare Oppenheimer and Barbie",
  "Is Deadpool ok for a 10 year old?",
  "Quiz me with movie trivia",
  "What should I watch tonight? Something funny",
  "Where can I watch Dune?",
];

const AGENT_LABEL: Record<string, string> = {
  plot: "📖 Plot",
  reviews: "⭐ Reviews",
  recommend: "🎯 Recommender",
  compare: "⚖️ Compare",
  similar: "🎬 More Like This",
  parental: "👨‍👩‍👧 Parental Guide",
  trivia: "🧠 Trivia",
  tonight: "🌙 Tonight",
  streaming: "📺 Where to Watch",
  smalltalk: "💬 Chat",
};

// Renders assistant replies as Markdown (GFM tables/lists/bold) with Tailwind styling.
// Descendant selectors keep us off the typography plugin, which isn't installed.
function Markdown({ content }: { content: string }) {
  return (
    <div
      className={[
        "text-[var(--foreground)]",
        "[&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0",
        "[&_strong]:font-semibold",
        "[&_h2]:mt-3 [&_h2]:mb-1.5 [&_h2]:font-heading [&_h2]:text-lg [&_h2]:font-semibold",
        "[&_h3]:mt-3 [&_h3]:mb-1 [&_h3]:font-heading [&_h3]:text-base [&_h3]:font-semibold",
        "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_li]:my-0.5",
        "[&_a]:text-[var(--accent)] [&_a]:underline",
        "[&_hr]:my-3 [&_hr]:border-[var(--border)]",
        "[&_table]:my-2 [&_table]:block [&_table]:w-full [&_table]:overflow-x-auto [&_table]:border-collapse",
        "[&_th]:border [&_th]:border-[var(--border)] [&_th]:px-2.5 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold",
        "[&_td]:border [&_td]:border-[var(--border)] [&_td]:px-2.5 [&_td]:py-1.5 [&_td]:align-top",
        "[&_code]:rounded [&_code]:bg-[var(--border)]/40 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.85em]",
      ].join(" ")}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, status]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setInput("");
    setBusy(true);
    setStatus("");

    // Drop any choice buttons from prior turns — they're answered once a new message is sent.
    const history: Msg[] = [
      ...messages.map((m): Msg => ({ ...m, choices: undefined })),
      { role: "user", content: trimmed },
    ];
    setMessages([...history, { role: "assistant", content: "" }]);

    const outgoing: ChatMessage[] = history.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const setLast = (patch: Partial<Msg>) =>
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
        return copy;
      });

    try {
      for await (const ev of streamChat(outgoing, sessionId)) {
        if (ev.type === "meta") setSessionId(ev.session_id);
        else if (ev.type === "agent") setLast({ agent: ev.name });
        else if (ev.type === "status") setStatus(ev.text);
        else if (ev.type === "choices") setLast({ choices: ev.options });
        else if (ev.type === "token") {
          setStatus("");
          setMessages((m) => {
            const copy = [...m];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, content: last.content + ev.text };
            return copy;
          });
        } else if (ev.type === "error") {
          setLast({ content: `⚠️ ${ev.message}` });
        }
      }
    } catch {
      setLast({ content: "⚠️ Could not reach the backend. Is it running on :8000?" });
    } finally {
      setStatus("");
      setBusy(false);
    }
  }

  const empty = messages.length === 0;

  return (
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col px-4">
      <header className="flex items-center gap-2.5 border-b border-[var(--border)] py-4">
        <span
          className="flex h-9 w-9 items-center justify-center rounded-xl text-lg"
          style={{ backgroundColor: "var(--accent)" }}
        >
          🎬
        </span>
        <h1 className="font-heading text-xl font-semibold tracking-tight">MovieBot</h1>
        <span className="ml-auto rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-xs text-[var(--muted)]">
          Phase 1
        </span>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto py-6">
        {empty ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 text-center">
            <div className="space-y-2">
              <h2 className="font-heading text-2xl font-semibold tracking-tight">
                What are we watching?
              </h2>
              <p className="text-[var(--muted)]">
                Ask about a movie&apos;s plot, its reviews, or get a recommendation.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => {
            const isLast = i === messages.length - 1;
            return (
              <div
                key={i}
                className={
                  m.role === "user" ? "flex justify-end" : "flex flex-col items-start"
                }
              >
                {m.role === "assistant" && m.agent && (
                  <span className="mb-1.5 ml-1 font-heading text-xs font-medium text-[var(--accent)]">
                    {AGENT_LABEL[m.agent] ?? m.agent}
                  </span>
                )}
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 leading-relaxed text-[var(--background)]"
                      : "max-w-[88%] rounded-2xl rounded-bl-md border border-[var(--border)] bg-[var(--surface)] px-4 py-3 leading-relaxed"
                  }
                  style={
                    m.role === "user" ? { backgroundColor: "var(--accent)" } : undefined
                  }
                >
                  {m.role === "user" ? (
                    m.content
                  ) : m.content ? (
                    <Markdown content={m.content} />
                  ) : isLast && busy ? (
                    <span className="inline-flex items-center gap-2 text-[var(--muted)]">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent)]" />
                      {status || "Thinking…"}
                    </span>
                  ) : (
                    ""
                  )}
                </div>
                {m.role === "assistant" && m.choices && m.choices.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-2">
                    {m.choices.map((c) => (
                      <button
                        key={c.value}
                        disabled={busy}
                        onClick={() => send(c.value)}
                        className="rounded-full border border-[var(--accent)] bg-[var(--surface)] px-4 py-2 text-sm text-[var(--accent)] transition hover:bg-[var(--accent)] hover:text-[var(--background)] disabled:opacity-50"
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="sticky bottom-0 flex gap-2 bg-[var(--background)] pb-5 pt-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message MovieBot…"
          className="flex-1 rounded-full border border-[var(--border)] bg-[var(--surface)] px-5 py-3 outline-none transition placeholder:text-[var(--muted)] focus:border-[var(--accent)]"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-full px-6 py-3 font-heading font-medium text-[var(--background)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          style={{ backgroundColor: "var(--accent)" }}
        >
          Send
        </button>
      </form>
    </main>
  );
}
