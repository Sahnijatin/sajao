// Runs a worklet the way the camera thread does: from its compiled code,
// in a fresh JavaScript context with no module scope, seeing only what the
// worklets compiler captured for it. A worklet that reaches for a module
// constant, a non-worklet helper or a value read too early (such as a
// default parameter) fails here exactly as it fails on a phone.
import { parse } from "@babel/parser";
import traverse from "@babel/traverse";

// Node's vm module, typed locally: the app's TypeScript setup has no Node types.
interface VmContext {
  readonly __vmContext?: never;
}
declare const require: (name: string) => unknown;
const vm = require("node:vm") as {
  createContext(sandbox: object): VmContext;
  runInContext(code: string, context: VmContext): unknown;
};

interface WorkletLike {
  (...args: unknown[]): unknown;
  __initData?: { code: string };
  __closure?: unknown;
}

export function isWorklet(value: unknown): value is WorkletLike {
  return typeof value === "function" && typeof (value as WorkletLike).__initData?.code === "string";
}

export function workletCode(fn: unknown): string {
  if (!isWorklet(fn))
    throw new Error(`${String((fn as { name?: string })?.name)} is not a worklet`);
  return fn.__initData!.code;
}

/** Built-ins every worklet runtime has. Anything else must be captured. */
const RUNTIME_GLOBALS = new Set([
  "Array",
  "Boolean",
  "Date",
  "Error",
  "Float32Array",
  "Float64Array",
  "Infinity",
  "Int32Array",
  "JSON",
  "Map",
  "Math",
  "NaN",
  "Number",
  "Object",
  "Set",
  "String",
  "Uint8Array",
  "Uint8ClampedArray",
  "isFinite",
  "isNaN",
  "undefined",
]);

/**
 * Names the compiled worklet reads that are neither captured nor runtime
 * built-ins, plus captured names read in default parameters (those run
 * before the captured values are unpacked).
 */
export function unsafeReferences(fn: unknown): string[] {
  const code = workletCode(fn);
  const ast = parse(code);
  const problems = new Set<string>();
  // `traverse` is a CommonJS default export.
  const walk = (traverse as unknown as { default?: typeof traverse }).default ?? traverse;
  walk(ast, {
    Program(path) {
      for (const name of Object.keys(path.scope.globals)) {
        if (!RUNTIME_GLOBALS.has(name)) problems.add(name);
      }
    },
    AssignmentPattern(path) {
      // Only parameters of the worklet itself: its captured values are
      // unpacked in the body, after default parameters are evaluated.
      if (!path.parentPath.isFunction() || !path.parentPath.parentPath?.isExpressionStatement())
        return;
      const right = path.get("right");
      const names = right.isIdentifier() ? [right.node.name] : [];
      right.traverse({
        Identifier(inner) {
          if (inner.isReferencedIdentifier()) names.push(inner.node.name);
        },
      });
      for (const name of names) problems.add(`default parameter reads ${name}`);
    },
  });
  return [...problems].sort();
}

/** A callable copy of `fn` that runs from its compiled code with no module scope. */
export function isolate<T extends (...args: never[]) => unknown>(fn: T): T {
  return isolateIn(fn, vm.createContext({})) as unknown as T;
}

function isolateIn(fn: unknown, context: VmContext): WorkletLike {
  const code = workletCode(fn);
  const compiled = vm.runInContext(`(${code})`, context) as (...args: unknown[]) => unknown;
  const captured = (fn as WorkletLike).__closure;
  const closure = Array.isArray(captured)
    ? captured.map((value) => isolateValue(value, context))
    : captured;
  const wrapper: WorkletLike = (...args: unknown[]) =>
    compiled.apply({ __closure: closure, _recur: wrapper }, args);
  return wrapper;
}

function isolateValue(value: unknown, context: VmContext): unknown {
  if (isWorklet(value)) return isolateIn(value, context);
  if (typeof value === "function") {
    // A plain function cannot run on the camera thread.
    return () => {
      throw new Error(`non-worklet function ${value.name || "(anonymous)"} called from a worklet`);
    };
  }
  return value;
}
