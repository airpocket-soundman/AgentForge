import { Fragment, type ReactNode } from "react";

// Minimal, dependency-free markdown for chat bubbles. Workers naturally write
// md (## headings, **bold**, lists, `code`); rendering it beats showing raw
// marks. We build React TEXT nodes only (no dangerouslySetInnerHTML), so model
// output can't inject markup. Supported: #/##/### headings, **bold**, `code`,
// - / ・ bullets, 1. ordered items, ``` fenced blocks, blank-line spacing.

function inline(text: string, keyBase: string): ReactNode[] {
  // Split on **bold** and `code` spans, preserving order.
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={`${keyBase}-b${i++}`}>{tok.slice(2, -2)}</strong>);
    else out.push(<code key={`${keyBase}-c${i++}`} className="md-code">{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function MdText({ text }: { text: string }) {
  const lines = (text ?? "").split("\n");
  const out: ReactNode[] = [];
  let inFence = false;
  let fence: string[] = [];
  lines.forEach((raw, idx) => {
    const line = raw.replace(/\s+$/, "");
    if (line.trimStart().startsWith("```")) {
      if (inFence) {
        out.push(<pre key={`f${idx}`} className="md-pre">{fence.join("\n")}</pre>);
        fence = [];
      }
      inFence = !inFence;
      return;
    }
    if (inFence) {
      fence.push(raw);
      return;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const cls = `md-h md-h${h[1].length}`;
      out.push(<div key={`h${idx}`} className={cls}>{inline(h[2], `h${idx}`)}</div>);
      return;
    }
    const li = /^\s*([-*・]|\d+[.)])\s+(.*)$/.exec(line);
    if (li) {
      const marker = li[1];
      const ordered = /^\d+[.)]$/.test(marker);
      out.push(
        <div
          key={`l${idx}`}
          className={`md-li ${ordered ? "md-ol" : "md-ul"}`}
          data-marker={ordered ? marker.replace(")", ".") : "・"}
        >
          {inline(li[2], `l${idx}`)}
        </div>
      );
      return;
    }
    if (line.trim() === "") {
      out.push(<div key={`s${idx}`} className="md-gap" />);
      return;
    }
    out.push(<Fragment key={`t${idx}`}>{inline(line, `t${idx}`)}{"\n"}</Fragment>);
  });
  if (inFence && fence.length) out.push(<pre key="ftail" className="md-pre">{fence.join("\n")}</pre>);
  return <span className="md">{out}</span>;
}
