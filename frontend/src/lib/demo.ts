// D111 writable demo: what the screen says in demo mode, and how a refused write reads. Display only.
// GET /api/v1/meta carries demo_writable (boolean); read at the top level or inside meta.meta, whichever BE sends.

export type DemoState = "live" | "demo_writable" | "demo_read_only";

type MetaLike = { demo_writable?: boolean; meta?: { mode?: string; demo_writable?: boolean } | null } | null | undefined;

export function demoState(m: MetaLike): DemoState {
  if (m?.meta?.mode !== "demo") return "live";
  return (m.demo_writable ?? m.meta.demo_writable) === true ? "demo_writable" : "demo_read_only";
}

/** Added to the existing snapshot line under the header when the demo is writable. */
export const SANDBOX_NOTE = "Changes stay in this sandbox and reset on restart.";

/** Shown near the insights in demo mode, writable or not; Refresh insights is disabled there. */
export const INSIGHTS_FROZEN =
  "Insights are frozen in this demo: generating new ones needs a live LLM connection and API key. They do not reflect changes made here.";

/** Any other 403 with a code (an action BE keeps off in the demo): a plain sentence, never the raw error. */
export const ACTION_OFF = "This action is turned off in this demo. Nothing was changed.";

/** The text an error note shows, and whether its code is shown next to it. demo_read_only keeps today's message. */
export function errorText(e: { status?: number; code?: string; message: string }): { text: string; showCode: boolean } {
  if (e.status === 403 && e.code === "insights_frozen_demo") return { text: INSIGHTS_FROZEN, showCode: false };
  if (e.status === 403 && e.code && e.code !== "demo_read_only" && e.code !== "http_error") return { text: ACTION_OFF, showCode: false };
  return { text: e.message, showCode: true };
}
