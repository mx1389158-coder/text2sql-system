# Web UI redesign (v1.2.0)

Verified on 2026-11-08 (Asia/Shanghai).

## Reference products

The redesign studied interaction patterns rather than copying source code or visual assets:

- [SQLChat](https://github.com/sqlchat/sqlchat): persistent database/schema navigation beside a
  chat-first SQL workspace.
- [DataChat](https://github.com/drharunyuksel/datachat): expandable schema explorer and explicit
  result presentation modes.
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT): continuous question, generation, execution and
  result workflow with visible system state.

## Implemented design

- Replaced the full dark terminal theme with a light professional data workspace and a focused dark
  navigation rail.
- Added page-level titles, descriptions, consistent inline SVG navigation icons and clearer runtime
  and API-key status controls.
- Rebuilt the query composer around a single dominant task, with strategy selection, examples,
  keyboard guidance and visible loading feedback.
- Placed Schema evidence and final read-only SQL side by side, added SQL copy, and separated the AST
  safety state from the code block.
- Added table/chart result tabs instead of rendering both views simultaneously.
- Reorganized the Schema page into a searchable table explorer, field detail panel and relationship
  graph.
- Added responsive layouts for desktop, tablet and narrow screens without changing backend APIs.

## Verification

- Vue/TypeScript typecheck: passed.
- Vite production build: passed.
- Browser acceptance: 8/8 passed, covering query, clarification, complex joins, security rejection,
  Schema graph, experiment page and Badcase page.
- Updated screenshots are stored in `docs/qa/screenshots/`.
