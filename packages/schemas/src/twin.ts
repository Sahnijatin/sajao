// The twin is built once from an immutable capture. A design is that twin
// plus an ordered list of edits; these pure functions apply the edits and
// derive the SpaceProfile view, so the render, plan, 3D view and shopping
// list all read one source. Nothing here invents a dimension: moved and
// rotated boxes keep their measured sizes, replaced and added items take
// their catalog sizes.
import type { SpaceProfile, SpaceTwin, TwinEdit, TwinObject } from "./generated/v1";

export interface EditProblem {
  edit_id: string;
  reason: string;
}

export interface AppliedTwin {
  /** The twin with every applicable edit applied. A new object: the input is never changed. */
  twin: SpaceTwin;
  /** Replaced objects and the catalog product that replaces each. */
  replacements: Record<string, string>;
  /** Ids of objects added from the catalog by edits. */
  added: string[];
  /** Edits that could not apply, with why. They are skipped, never half applied. */
  problems: EditProblem[];
}

const ADDED_CATEGORY = "catalog_product";

export function applyEdits(twin: SpaceTwin, edits: readonly TwinEdit[]): AppliedTwin {
  const next: SpaceTwin = structuredClone(twin);
  const replacements: Record<string, string> = {};
  const added: string[] = [];
  const problems: EditProblem[] = [];
  const seen = new Set<string>();
  const objectById = (id: string): TwinObject | undefined =>
    next.objects.find((object) => object.id === id);

  for (const edit of edits) {
    const problem = (reason: string) => problems.push({ edit_id: edit.id, reason });
    if (seen.has(edit.id)) {
      problem("duplicate edit id");
      continue;
    }
    seen.add(edit.id);

    switch (edit.op) {
      case "move":
      case "rotate":
      case "remove":
      case "replace": {
        const target = objectById(edit.object_id);
        if (!target) {
          problem("unknown object");
          break;
        }
        if (target.state === "remove") {
          problem("object was removed");
          break;
        }
        if (edit.op === "move") {
          target.box.center = { ...edit.to };
          if (target.state === "keep") target.state = "move";
        } else if (edit.op === "rotate") {
          target.box.yaw_deg = edit.yaw_deg;
          if (target.state === "keep") target.state = "move";
        } else if (edit.op === "remove") {
          target.state = "remove";
          delete replacements[target.id];
        } else {
          target.state = "replace";
          target.box.width = { ...edit.product_size.width };
          target.box.depth = { ...edit.product_size.depth };
          target.box.height = { ...edit.product_size.height };
          replacements[target.id] = edit.product_id;
        }
        break;
      }
      case "add": {
        if (objectById(edit.id)) {
          problem("id already used by an object");
          break;
        }
        next.objects.push({
          id: edit.id,
          category: ADDED_CATEGORY,
          label: edit.label,
          box: {
            center: { ...edit.to },
            yaw_deg: edit.yaw_deg,
            width: { ...edit.product_size.width },
            depth: { ...edit.product_size.depth },
            height: { ...edit.product_size.height },
          },
          detection: { source: "user", confidence: 1 },
          views: [],
          catalog_matches: [{ product_id: edit.product_id, similarity: 1, fits_box: true }],
          state: "keep",
        });
        added.push(edit.id);
        break;
      }
      case "restyle_surface": {
        const surface = next.shell.surfaces.find((candidate) => candidate.id === edit.surface_id);
        if (!surface) {
          problem("unknown surface");
          break;
        }
        surface.material = structuredClone(edit.material);
        break;
      }
    }
  }
  return { twin: next, replacements, added, problems };
}

const ACTION: Record<TwinObject["state"], "keep" | "replace" | "remove"> = {
  keep: "keep",
  move: "keep",
  replace: "replace",
  remove: "remove",
};

/**
 * The SpaceProfile is a view of the twin: the shell and the user's existing
 * items, each with their keep, replace or remove choice. Items added from the
 * catalog belong to the design, not to the space, so they are left out.
 */
export function spaceProfileFromTwin(
  twin: SpaceTwin,
  options: { id: string; created_at: string; redo?: SpaceProfile["redo"] },
  edits: readonly TwinEdit[] = [],
): SpaceProfile {
  const applied = applyEdits(twin, edits);
  const { shell } = applied.twin;
  const added = new Set(applied.added);
  const measured = (source: string) => source === "measured";
  const verified =
    measured(shell.ceiling_height.source) &&
    shell.walls.every((wall) => measured(wall.length.source));
  return {
    schema_version: twin.schema_version,
    id: options.id,
    capture_id: twin.capture_id,
    space_type: twin.space_type,
    space_type_source: twin.space_type_source,
    extent: twin.extent,
    extent_source: twin.extent_source,
    redo: options.redo ?? { scope: "all" },
    created_at: options.created_at,
    verification: verified ? "verified" : "estimated",
    floor_polygon: structuredClone(shell.floor_polygon),
    walls: structuredClone(shell.walls),
    ceiling_height: { ...shell.ceiling_height },
    openings: structuredClone(shell.openings),
    fixtures: structuredClone(shell.fixtures),
    existing_items: applied.twin.objects
      .filter((object) => !added.has(object.id))
      .map((object) => ({
        id: object.id,
        label: object.label,
        center: { x_m: object.box.center.x_m, y_m: object.box.center.y_m },
        width: { ...object.box.width },
        depth: { ...object.box.depth },
        height: { ...object.box.height },
        rotation_deg: object.box.yaw_deg,
        action: ACTION[object.state],
      })),
    direction: structuredClone(twin.direction),
    scale: structuredClone(twin.scale),
  };
}
