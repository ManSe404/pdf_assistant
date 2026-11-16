# 0002. Freeze pdf_assistant as a demo; new features go to document-buddy

## Status

Accepted (2026-11-10, commit "docs: freeze pdf_assistant as a demo; new features go to
document-buddy").

## Context

After the 2026-11-05 rewrite ([ADR 0001](0001-rewrite-on-fastapi.md)) the app works: one PDF per
conversation, cited answers, the vote experiment. What would come next for it (scans and OCR,
folders, several documents, a shared knowledge base) already exists in
[document-buddy](https://github.com/ManSe404/document-buddy), which is moving to the Mosaic library.

## Decision

pdf_assistant is frozen as a demo. No new features are added here; new features go to
document-buddy. Bug fixes are still welcome.

## Consequences

- The repository keeps no roadmap; its status is stated in `README.md` and `docs/README.md`.
- What the app does not do (OCR, several documents per conversation, folders, a shared knowledge
  base) stays out of scope here, as `docs/product/vision.md` lists.
