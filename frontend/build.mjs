// Production build: bundles src/main.tsx and the stylesheet with content-hashed names,
// then writes dist/index.html. `--watch` rebuilds on change (served by the API at :8000).
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");
const out = "dist";

function writeIndex(result) {
  const outputs = Object.keys(result.metafile.outputs).map((p) => p.replace(/^dist\//, ""));
  const js = outputs.find((p) => p.endsWith(".js"));
  const css = outputs.find((p) => p.endsWith(".css"));
  const html = readFileSync("index.html", "utf8")
    .replace("<!--CSS-->", `<link rel="stylesheet" href="/${css}">`)
    .replace("<!--JS-->", `<script type="module" src="/${js}"></script>`);
  writeFileSync(join(out, "index.html"), html);
  for (const file of readdirSync("public")) copyFileSync(join("public", file), join(out, file));
  const digest = createHash("sha256").update(html).digest("hex").slice(0, 8);
  console.log(`built ${js} ${css} index:${digest}`);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const options = {
  entryPoints: { app: "src/main.tsx" },
  bundle: true,
  outdir: join(out, "assets"),
  entryNames: "[name]-[hash]",
  assetNames: "[name]-[hash]",
  loader: { ".woff": "file" },
  format: "esm",
  target: ["es2020", "chrome90", "firefox90", "safari15"],
  minify: !watch,
  sourcemap: watch ? "inline" : false,
  metafile: true,
  legalComments: "none",
  define: { "process.env.NODE_ENV": JSON.stringify(watch ? "development" : "production") },
  plugins: [
    {
      name: "index-html",
      setup(build) {
        build.onEnd((result) => {
          if (result.errors.length === 0) writeIndex(result);
        });
      },
    },
  ],
};

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
  console.log("watching src/ ...");
} else {
  await esbuild.build(options);
}
