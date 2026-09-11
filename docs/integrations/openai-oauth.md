# `openai-oauth` integration evaluation

Reviewed 2026-09-06 against the upstream `main` branch. This is an engineering and release-risk
assessment, not legal advice.

## Decision

ShinyColorsPet may support `openai-oauth` as an **experimental, consent-gated local
OpenAI-compatible proxy**. It is never the default provider. The public executable does not bundle
Node.js, the NPM package, or OAuth credentials; after the user accepts the personal-use disclaimer,
the application downloads pinned local prerequisites, verifies the official Node checksum, invokes
the pinned package, and opens its browser login. ShinyColorsPet must not read `~/.codex/auth.json`,
receive refresh/access tokens, or describe the integration as official or OpenAI-endorsed.

The supported boundary is:

1. the user reviews and accepts a disclaimer that requires their own account and forbids credential
   sharing, token pooling, resale, and restriction bypass;
2. ShinyColorsPet provisions Node.js 22.23.2 and `openai-oauth` 2.0.0 in its private data directory
   on first use, then starts the browser login and loopback proxy;
3. the proxy listens only on `http://127.0.0.1:10531/v1` and ShinyColorsPet calls it through the
   existing OpenAI-compatible client;
4. every user remains subject to their plan limits, OpenAI terms, and the third-party project risk.

## Basis

- The upstream project is Apache-2.0 but explicitly unofficial and not endorsed by OpenAI.
- Its CLI exposes `/v1/chat/completions`, `/v1/responses`, and `/v1/models` on loopback and stores
  credentials in the same local location used by Codex.
- Its default upstream is the ChatGPT Codex backend, not the documented OpenAI API base URL. The
  upstream project warns that credentials must be treated like passwords and that the underlying
  service may change or be disabled.
- OpenAI documents ChatGPT sign-in for official Codex clients and says credentials are stored
  locally. OpenAI's public Sign in with ChatGPT feature is for participating external apps and
  shares identity information; it does not by itself grant third-party access to conversations,
  files, tokens, or billing data.
- OpenAI terms prohibit credential sharing and bypassing rate limits, restrictions, protective
  measures, or usage limits. Therefore ShinyColorsPet must never pool credentials, proxy one
  user's account for others, or represent this path as a way around API billing or product limits.

## Gates before any hosted or token-direct integration

- Written confirmation from OpenAI that this desktop use of the Codex OAuth backend is supported.
- Independent security review of third-party credential storage, token refresh, callback binding,
  the pinned NPM dependency graph, runtime download, and revocation behavior.
- A privacy disclosure and explicit consent screen covering what desktop/chat context is sent.
- Failure UX that cleanly falls back to a documented OpenAI-compatible API provider when the unofficial
  endpoint changes.

Sources: [upstream repository](https://github.com/EvanZhouDev/openai-oauth/tree/main),
[OpenAI Codex CLI sign-in documentation](https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt),
[OpenAI Sign in with ChatGPT documentation](https://help.openai.com/en/articles/20001410-sign-in-with-chatgpt),
and [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/).
