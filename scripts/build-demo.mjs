// Müşteri demosu: `vite build --mode demo` çıktısını tek bir HTML sayfasına gömer.
// Kullanım: node scripts/build-demo.mjs <çıktı.html>
// Sayfa yalnızca örnek verilerle (src/lib/mock.ts) çalışır ve "DEMO" şeridi gösterir.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const out = process.argv[2];
if (!out) {
  console.error("Kullanım: node scripts/build-demo.mjs <çıktı.html>");
  process.exit(2);
}

const vite = join("node_modules", "vite", "bin", "vite.js");
execFileSync(process.execPath, [vite, "build", "--mode", "demo"], { stdio: "inherit" });

const dist = "dist-demo";
const html = readFileSync(join(dist, "index.html"), "utf8");
const asset = (pattern) => {
  const match = html.match(pattern);
  if (!match) throw new Error(`Derleme çıktısında bulunamadı: ${pattern}`);
  return readFileSync(join(dist, match[1]), "utf8");
};
const css = asset(/href="\/?([^"]+\.css)"/);
// Gömülü betikte "</script" dizisi sayfayı erken kapatmasın.
const js = asset(/src="\/?([^"]+\.js)"/).replaceAll("</script", "<\\/script");

const page = `<title>Etkileşim Takip</title>
<meta name="author" content="created by axthrowa">
<style>${css}</style>
<div id="root"></div>
<script type="module">${js}</script>
`;
writeFileSync(resolve(out), page, "utf8");
console.log(`Demo sayfası: ${resolve(out)} (${Math.round(page.length / 1024)} KB)`);
