// Builds everything derived from the JSON Schema sources in schemas/v1:
//   generated/v1.schema.json               one bundled schema with every definition
//   src/generated/v1.ts                    TypeScript types
//   python/sajao_schemas/generated/v1.py   Pydantic models
// The sources are the contract. Never edit generated files by hand.
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const VERSION = "v1";
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = join(root, "schemas", VERSION);

const sources = new Map(
  readdirSync(sourceDir)
    .filter((name) => name.endsWith(".schema.json"))
    .sort()
    .map((name) => [name, JSON.parse(readFileSync(join(sourceDir, name), "utf8"))]),
);

// Every reference becomes a local reference into one flat set of definitions.
function rewriteRefs(node, file) {
  if (Array.isArray(node)) return node.map((child) => rewriteRefs(child, file));
  if (node === null || typeof node !== "object") return node;
  const out = {};
  for (const [key, value] of Object.entries(node)) {
    if (key !== "$ref") {
      out[key] = rewriteRefs(value, file);
      continue;
    }
    const [target, fragment = ""] = value.split("#");
    const targetFile = target || file;
    const source = sources.get(targetFile);
    if (!source) throw new Error(`${file}: unknown reference ${value}`);
    const name = fragment ? fragment.replace("/$defs/", "") : source.title;
    if (fragment && !(name in (source.$defs ?? {}))) {
      throw new Error(`${file}: unknown reference ${value}`);
    }
    out.$ref = `#/$defs/${name}`;
  }
  return out;
}

const defs = {};
const topLevel = [];
function add(name, schema, file) {
  if (name in defs) throw new Error(`${file}: duplicate definition name ${name}`);
  defs[name] = rewriteRefs(schema, file);
}
for (const [file, source] of sources) {
  const { $schema: _schema, $id: _id, $defs: localDefs = {}, ...body } = source;
  if (body.type === "object") {
    add(body.title, body, file);
    topLevel.push(body.title);
  }
  for (const [name, schema] of Object.entries(localDefs)) add(name, schema, file);
}

const bundle = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: `https://schemas.sajao.app/${VERSION}/bundle.schema.json`,
  title: "SajaoContract",
  description: `Generated from schemas/${VERSION}. Do not edit.`,
  "x-top-level": topLevel,
  $defs: Object.fromEntries(Object.entries(defs).sort(([a], [b]) => a.localeCompare(b))),
};
const bundlePath = join(root, "generated", `${VERSION}.schema.json`);
mkdirSync(dirname(bundlePath), { recursive: true });
writeFileSync(bundlePath, JSON.stringify(bundle, null, 2) + "\n");

// A description beside a $ref makes the TypeScript generator emit a duplicate
// type (Money1, Dimension1), so siblings of $ref are dropped for that step only.
function refsOnly(node) {
  if (Array.isArray(node)) return node.map(refsOnly);
  if (node === null || typeof node !== "object") return node;
  if ("$ref" in node) return { $ref: node.$ref };
  return Object.fromEntries(Object.entries(node).map(([key, value]) => [key, refsOnly(value)]));
}

const banner = `/* Generated from schemas/${VERSION} by scripts/generate.mjs. Do not edit. */`;
const types = await compile(refsOnly(bundle), "SajaoContract", {
  bannerComment: banner,
  additionalProperties: false,
  unreachableDefinitions: true,
  format: false,
});
const typesPath = join(root, "src", "generated", `${VERSION}.ts`);
mkdirSync(dirname(typesPath), { recursive: true });
writeFileSync(typesPath, types);

const modelsPath = join(root, "python", "sajao_schemas", "generated", `${VERSION}.py`);
mkdirSync(dirname(modelsPath), { recursive: true });
execFileSync(
  "uv",
  [
    "run",
    "datamodel-codegen",
    ...["--input", bundlePath, "--input-file-type", "jsonschema"],
    ...["--output", modelsPath, "--output-model-type", "pydantic_v2.BaseModel"],
    ...["--target-python-version", "3.13", "--formatters", "ruff-format"],
    "--use-title-as-name",
    "--use-schema-description",
    "--use-standard-collections",
    "--use-union-operator",
    "--field-constraints",
    "--use-annotated",
    "--collapse-root-models",
    "--enum-field-as-literal",
    "all",
    "--disable-timestamp",
    "--custom-file-header",
    `# Generated from schemas/${VERSION} by scripts/generate.mjs. Do not edit.`,
  ],
  { stdio: "inherit" },
);
console.log(`Generated ${topLevel.length} objects: ${topLevel.join(", ")}`);
