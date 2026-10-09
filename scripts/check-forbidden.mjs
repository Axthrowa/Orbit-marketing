// CONTRIBUTING.md'deki yasak kısayolları denetler (npm run lint).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const RULES = [
  { name: "açık `any`", pattern: /(:\s*any\b|\bas\s+any\b|<any>|any\[\])/ },
  { name: "@ts-ignore / @ts-nocheck", pattern: /@ts-(ignore|nocheck)/ },
  { name: "boş catch", pattern: /catch\s*(\([^)]*\))?\s*\{\s*\}/ },
  { name: "TODO/FIXME", pattern: /\b(TODO|FIXME)\b/ },
  { name: "sabit token/parola", pattern: /(password|token|secret|api[_-]?key)\s*[:=]\s*["'][^"']{8,}["']/i },
];

const SKIP = new Set(["mock.ts"]); // yalnızca önizleme; sabit PIN burada bilinçli

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

let failures = 0;
for (const file of walk("src").filter((f) => /\.(ts|tsx)$/.test(f))) {
  if (SKIP.has(file.split(/[\\/]/).pop())) continue;
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, index) => {
    for (const rule of RULES) {
      if (rule.pattern.test(line) && !/forbidden-ok/.test(line)) {
        console.error(`${file}:${index + 1}: ${rule.name}: ${line.trim()}`);
        failures += 1;
      }
    }
  });
}

if (failures > 0) {
  console.error(`\n${failures} yasak desen bulundu.`);
  process.exit(1);
}
console.log("Yasak desen yok.");
