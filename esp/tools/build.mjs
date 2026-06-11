import { cp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";

const espDir = path.resolve(import.meta.dir, "..");
const buildDir = path.join(espDir, "build");
const tempDir = path.join(espDir, ".build-tmp");

await rm(buildDir, { recursive: true, force: true });
await rm(tempDir, { recursive: true, force: true });
await mkdir(path.join(buildDir, "app", "www"), { recursive: true });
await mkdir(tempDir, { recursive: true });

const result = await Bun.build({
  entrypoints: [path.join(espDir, "web", "app.js")],
  outdir: tempDir,
  minify: true,
  target: "browser",
});
if (!result.success) {
  for (const log of result.logs) console.error(log);
  process.exit(1);
}

const html = await readFile(path.join(espDir, "web", "index.html"), "utf8");
const css = await readFile(path.join(espDir, "web", "app.css"), "utf8");
const js = await readFile(path.join(tempDir, "app.js"), "utf8");
const minifiedCss = css
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\s+/g, " ")
  .replace(/\s*([{}:;,>])\s*/g, "$1")
  .trim();
const page = html
  .replace("/*__CSS__*/", minifiedCss)
  .replace("/*__JS__*/", js)
  .replace(/>\s+</g, "><")
  .trim();

await writeFile(
  path.join(buildDir, "app", "www", "index.html.gz"),
  gzipSync(Buffer.from(page), { level: 9 }),
);
await cp(path.join(espDir, "src", "boot.py"), path.join(buildDir, "boot.py"));
await cp(path.join(espDir, "src", "main.py"), path.join(buildDir, "main.py"));
const sourceFilter = (source) =>
  !source.includes("__pycache__") && !source.endsWith(".pyc");
await cp(path.join(espDir, "src", "app"), path.join(buildDir, "app"), {
  recursive: true,
  filter: sourceFilter,
});
await cp(path.join(espDir, "lib"), path.join(buildDir, "lib"), {
  recursive: true,
  filter: sourceFilter,
});
await rm(tempDir, { recursive: true, force: true });

async function filesIn(directory) {
  const glob = new Bun.Glob("**/*");
  const files = [];
  for await (const item of glob.scan({ cwd: directory, onlyFiles: true })) {
    files.push(item);
  }
  return files.sort();
}

let total = 0;
console.log("Atmospheric firmware build");
for (const file of await filesIn(buildDir)) {
  const size = (await stat(path.join(buildDir, file))).size;
  total += size;
  console.log(`${String(size).padStart(7)}  ${file}`);
}
console.log(`${String(total).padStart(7)}  total`);

const limit = Number(process.env.ESP_BUILD_LIMIT || 180000);
if (total > limit) {
  throw new Error(`Build is ${total} bytes, over the ${limit} byte limit`);
}
