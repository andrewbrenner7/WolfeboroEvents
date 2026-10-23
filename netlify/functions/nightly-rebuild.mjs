// Nightly rebuild so the events pages drop past events on their own.
// The events builders hide anything whose end date (or last date) is before
// the build date, so a fresh build each night keeps the page current.
// Runs at 08:15 UTC: 4:15 a.m. EDT / 3:15 a.m. EST, and after midnight Pacific.
// The build hook URL lives in the NIGHTLY_BUILD_HOOK_URL environment variable
// (set in Netlify, never committed and never logged).
export default async () => {
  const hook = process.env.NIGHTLY_BUILD_HOOK_URL;
  if (!hook) {
    console.log("nightly-rebuild: NIGHTLY_BUILD_HOOK_URL is not set, skipping");
    return new Response("skipped", { status: 200 });
  }
  const res = await fetch(hook + (hook.includes("?") ? "&" : "?") + "trigger_title=Nightly+events+rebuild", { method: "POST" });
  console.log("nightly-rebuild: build hook responded " + res.status);
  return new Response(res.ok ? "ok" : "hook error", { status: res.ok ? 200 : 502 });
};

export const config = { schedule: "15 8 * * *" };
