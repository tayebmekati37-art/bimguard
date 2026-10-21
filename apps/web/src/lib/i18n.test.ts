// Lightweight parity check for the translation dictionaries.
// Not run by the app; used by CI or manually via `npx tsx i18n.test.ts`.
import { ALL_DICTS, type Locale } from "./i18n";

const LOCALES: Locale[] = ["en", "ja"];
const reference = Object.keys(ALL_DICTS.en).sort();

let failures = 0;

for (const locale of LOCALES) {
  if (locale === "en") continue;
  const keys = Object.keys(ALL_DICTS[locale]).sort();
  const missing = reference.filter((k) => !keys.includes(k));
  const extra = keys.filter((k) => !reference.includes(k));
  if (missing.length) {
    console.error(`${locale}: missing keys:`, missing);
    failures++;
  }
  if (extra.length) {
    console.error(`${locale}: extra keys:`, extra);
    failures++;
  }
  // Check no blank values
  for (const k of keys) {
    const v = ALL_DICTS[locale][k];
    if (!v || !v.trim()) {
      console.error(`${locale}: empty value for ${k}`);
      failures++;
    }
  }
}

if (failures > 0) {
  console.error(`FAIL - ${failures} issue(s)`);
  process.exit(1);
}
console.log(`OK - ${reference.length} keys present in ${LOCALES.length} locales`);