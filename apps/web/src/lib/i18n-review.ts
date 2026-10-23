/**
 * Review status of the Japanese translations.
 *
 * The current state is: every Japanese string in `i18n.ts` is a
 * machine-assisted translation. None has been reviewed by a
 * Japanese-speaking BIM/CIM engineer. The English text is the source
 * of truth.
 *
 * When a translator reviews a subset of keys, add them to
 * REVIEWED_KEYS. When the entire dictionary has been reviewed by a
 * qualified specialist, set IS_PROFESSIONALLY_REVIEWED to true and
 * update docs/architecture/i18n.md.
 *
 * Nothing in the UI blocks on this; the information is exposed in the
 * Settings page so a user can see the current review state.
 */

export const REVIEWED_KEYS: ReadonlySet<string> = new Set([
  // Add keys here only after a Japanese-speaking reviewer has confirmed
  // them. Do not add a key because "it looks fine." The point of this
  // list is to be a truthful record.
]);

export const IS_PROFESSIONALLY_REVIEWED = false;

export function isReviewed(key: string): boolean {
  return REVIEWED_KEYS.has(key);
}