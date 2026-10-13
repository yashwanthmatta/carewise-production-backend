// Cloudflare Email Worker for DocBridge email intake.
// Email Routing hands every message sent to *@in.<your domain> to this Worker, which
// posts the raw message to the API. Set one Worker secret:
//   INTAKE_URL = https://<api host>/inbound/email/<CAREWISE_INBOUND_EMAIL_TOKEN>
// The envelope recipient is added as X-Original-To so a Bcc'd address still matches.
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
};
