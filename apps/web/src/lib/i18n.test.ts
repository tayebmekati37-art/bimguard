// Parity + review check for translation dictionaries.
// Run: npx tsx src/lib/i18n.test.ts
import { ALL_DICTS, type Locale } from "./i18n";
import { IS_PROFESSIONALLY_REVIEWED, REVIEWED_KEYS } from "./i18n-review";

const LOCALES: Locale[] = ["en", "ja"];
const reference = Object.keys(ALL_DICTS.en).sort();

let failures = 0;

for (const locale of LOCALES) {
  if (locale === "en") continue;
  const keys = Object.keys(ALL_DICTS[locale]).sort();
  const missing = reference.filter((k) => !keys.includes(k));
  const extra = keys.filter((k) => !reference.includes(k));
  if (missing.length) {
    console.error(`${locale}: missing keys (${missing.length}):`, missing.slice(0, 20));
    failures++;
  }
  if (extra.length) {
    console.error(`${locale}: extra keys (${extra.length}):`, extra.slice(0, 20));
    failures++;
  }
  for (const k of keys) {
    const v = ALL_DICTS[locale][k];
    if (!v || !v.trim()) {
      console.error(`${locale}: empty value for ${k}`);
      failures++;
    }
  }
}

// If not professionally reviewed, REVIEWED_KEYS may be empty - that's fine.
// If it claims review, at least half the keys must be marked.
if (IS_PROFESSIONALLY_REVIEWED) {
  const reviewed = REVIEWED_KEYS.size;
  const total = reference.length;
  if (reviewed < total / 2) {
    console.error(
      `IS_PROFESSIONALLY_REVIEWED is true but only ${reviewed}/${total} keys are marked reviewed.`,
    );
    failures++;
  }
}

if (failures > 0) {
  console.error(`FAIL - ${failures} issue(s)`);
  process.exit(1);
}

const reviewStatus = IS_PROFESSIONALLY_REVIEWED
  ? "professionally reviewed"
  : `machine-assisted (${REVIEWED_KEYS.size}/${reference.length} keys individually reviewed)`;
console.log(`OK - ${reference.length} keys in ${LOCALES.length} locales; review status: ${reviewStatus}`);