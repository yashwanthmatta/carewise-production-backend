// Cloudflare Worker for FollowThrough Health: DocBridge email intake, plus the
// scheduled jobs (reminder calls every 5 minutes, nightly data cleanup).
//
// Secrets (Worker > Settings > Variables and Secrets):
//   INTAKE_URL = https://<api host>/inbound/email/<CAREWISE_INBOUND_EMAIL_TOKEN>
//   CRON_TOKEN = the same value as CAREWISE_REMINDER_CRON_TOKEN on the Render API service
// Cron triggers (Worker > Settings > Triggers): "*/5 * * * *" and "17 7 * * *".
//
// GitHub's scheduled workflows only ran every 2 to 6 hours in practice, and a reminder
// is created only when its time falls in the last 15 minutes, so most reminders were
// skipped. Cloudflare's cron runs on time. The calls also keep the free API awake.
function apiBase(env) {
  return new URL(env.INTAKE_URL).origin;
}

export default {
  async email(message, env) {
    const raw = new Uint8Array(await new Response(message.raw).arrayBuffer());
    const header = new TextEncoder().encode(`X-Original-To: ${message.to}\r\n`);
    const body = new Uint8Array(header.length + raw.length);
    body.set(header);
    body.set(raw, header.length);
    const response = await fetch(env.INTAKE_URL, {
      method: "POST",
      headers: { "content-type": "message/rfc822" },
      body,
    });
    if (!response.ok) message.setReject(`Lab intake is unavailable (${response.status}). Please try again later.`);
  },

  async scheduled(event, env) {
    if (!env.CRON_TOKEN || !env.INTAKE_URL) return;
    const path = event.cron === "17 7 * * *" ? "/maintenance/purge" : "/reminders/dispatch";
    const response = await fetch(`${apiBase(env)}${path}`, {
      method: "POST",
      headers: { "X-CareWise-Cron-Token": env.CRON_TOKEN },
    });
    // A failed run shows in the Worker's logs; the next run 5 minutes later tries again.
    if (!response.ok) console.log(`FollowThrough Health ${path} returned ${response.status}`);
  },
};
