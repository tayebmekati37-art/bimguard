# i18n wiring checklist (M21b)

The dictionary in `lib/i18n.ts` has ~180 keys in each locale. Wiring is
the mechanical task of replacing hardcoded English with `t("key")` calls
in each page or component. This document tracks progress.

## Status

| File | Strings | Status | Notes |
| :--- | :--- | :--- | :--- |
| `components/AppShell.tsx` | 8 | wired (M18) | nav + role label |
| `components/LanguageSwitcher.tsx` | 1 | wired (M18) | aria-label |
| `components/NotificationBell.tsx` | 2 | wired (M21b-i) | text + aria-label |
| `components/ExplainButton.tsx` | 4 | wired (M21b-i) | button + badges + fallback |
| `app/projects/[id]/ask/page.tsx` | 12 | wired (M21) | |
| `app/projects/[id]/reports/page.tsx` | 18 | wired (M21) | |
| `app/audit/page.tsx` | 15 | wired (M21) | |
| `app/notifications/page.tsx` | 11 | wired (M21) | |
| `app/settings/page.tsx` | 8 | wired (M21) | + translation notice |
| `app/login/page.tsx` | ~8 | pending (M21b-ii) | needs source |
| `app/dashboard/page.tsx` | ~15 | pending (M21b-ii) | needs source |
| `app/projects/page.tsx` | ~20 | pending (M21b-ii) | needs source |
| `app/projects/[id]/page.tsx` | ~50 | pending (M21b-ii) | biggest file |
| `app/settings/profiles/page.tsx` | ~20 | pending (M21b-iii) | |
| `app/rules/page.tsx` | ~12 | pending (M21b-iii) | |
| `app/projects/[id]/dependencies/page.tsx` | ~10 | pending (M21b-iii) | |
| `app/projects/[id]/impact/page.tsx` | ~10 | pending (M21b-iii) | |
| `app/projects/[id]/validation/page.tsx` | ~15 | pending (M21b-iii) | |
| `app/revisions/[id]/compare/page.tsx` | ~8 | pending (M21b-iii) | |
| `components/ui.tsx` | ~5 | pending (M21b-iii) | StatusBadge, SeverityBadge, ErrorNote, Pager labels |
| `components/HealthPanel.tsx` | ~10 | pending (M21b-iii) | |
| `components/ElementsDialog.tsx` | ~8 | pending (M21b-iii) | |
| `components/SearchBox.tsx` | ~3 | pending (M21b-iii) | |

## How to wire a file

1. Run the audit to see what is in that file:

       python scripts/i18n-audit.py

2. Add `import { useT } from "@/lib/i18n";` at the top of the component file.
3. Inside the component function: `const { t } = useT();`
4. Replace each hardcoded string with `t("key")`.
5. If a string has no key yet, add it to both `DICTS.en` and `DICTS.ja` in `lib/i18n.ts` first.
6. Run:

       npx tsc --noEmit
       npx tsx src/lib/i18n.test.ts

7. Run the audit again. The file should drop to zero findings.
8. Move it from `pending` to `wired` in the table above.

## What the audit tool tells you

For each finding it shows:

- `file:line` - where
- `[kind]` - attribute (attr:placeholder), JSX text (jsx-text), or object literal (obj-literal)
- the string itself
- `-> key` - the suggested key from a curated English-to-key map, or `(no key yet)`

The suggested key is a heuristic, not a rule. If the text on screen differs
from the mapped English (for example a template literal "Sign in to {name}"),
the suggestion will be absent - that is correct, and you need a new key.

## Why this is not automated

A pure regex replace of English into t("key") in JSX is unsafe because:

- The same English string might appear in a comment, a CSS class, or a data field
- A page might import a component whose label is passed as children
- Pluralization and interpolation need manual judgment

The audit tool narrows the search; the actual editing is done by hand, one
file at a time, with tsc and the parity test as safety nets.

## See also

- `docs/architecture/i18n.md` - translation coverage and review status
- `lib/i18n-review.ts` - review tracking (machine-assisted vs reviewed)