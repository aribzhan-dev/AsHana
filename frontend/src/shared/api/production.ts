import type { components } from "./schema";
import { ApiError, record, request } from "./http";
import { item, operation } from "./inventory";
import { productionRu as t } from "../locales/production";
export type Recipe = components["schemas"]["RecipeResponse"];
export type RecipeInput = components["schemas"]["RecipeInput"];
export type Production = components["schemas"]["ProductionResponse"];
export type ProductionInput = components["schemas"]["ProductionInput"];
export type RawBatch = components["schemas"]["RawBatchResponse"];
export type RawUnit = RecipeInput["portion_unit"];
function invalid(): never {
  throw new ApiError(0, t.invalidData);
}
function list<T>(value: unknown, parse: (v: unknown) => T): T[] {
  if (!Array.isArray(value)) return invalid();
  return value.map(parse);
}
function strings(value: Record<string, unknown>, keys: string[]) {
  if (keys.some((key) => typeof value[key] !== "string")) invalid();
}
function decimal(value: unknown) {
  if (typeof value !== "string" || !/^\d+(\.\d+)?$/.test(value)) invalid();
}
function whole(value: unknown) {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1)
    invalid();
}
function date(value: unknown) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value)))
    invalid();
}
function rawUnit(value: unknown) {
  if (value !== "kg" && value !== "l") invalid();
}
function outputUnit(value: unknown) {
  if (value !== "pcs" && value !== "portion") invalid();
}
function recipe(value: unknown): Recipe {
  if (!record(value)) return invalid();
  strings(value, [
    "id",
    "output_item_id",
    "output_name",
    "instructions",
    "actor_id",
  ]);
  whole(value.version);
  whole(value.expected_yield);
  decimal(value.portion_quantity);
  rawUnit(value.portion_unit);
  outputUnit(value.output_unit);
  date(value.created_at);
  list(value.lines, (line) => {
    if (!record(line)) return invalid();
    strings(line, ["item_id", "item_name"]);
    decimal(line.quantity);
    rawUnit(line.unit);
    return line;
  });
  return value as Recipe;
}
function rawBatch(value: unknown): RawBatch {
  if (!record(value)) return invalid();
  strings(value, ["id", "item_id", "item_name", "label"]);
  if (
    !["active", "suspended", "expired", "exhausted", "written_off"].includes(
      String(value.status),
    )
  )
    invalid();
  decimal(value.available);
  date(value.expires_at);
  rawUnit(value.unit);
  return value as RawBatch;
}
function production(value: unknown): Production {
  if (!record(value)) return invalid();
  strings(value, ["id", "recipe_id", "output_name", "label", "actor_id"]);
  whole(value.recipe_version);
  whole(value.actual_yield);
  outputUnit(value.output_unit);
  date(value.created_at);
  date(value.expires_at);
  list(value.consumption, (line) => {
    if (!record(line)) return invalid();
    strings(line, [
      "item_id",
      "item_name",
      "batch_id",
      "batch_label",
      "movement_id",
    ]);
    decimal(line.quantity);
    rawUnit(line.unit);
    return line;
  });
  return value as Production;
}
const write = (path: string, body: unknown, key: string) =>
  request(`/production${path}`, "POST", body, { "Idempotency-Key": key }).then(
    operation,
  );
export const productionApi = {
  recipe: (id: string) =>
    request(`/production/recipes/${encodeURIComponent(id)}`).then(recipe),
  recipes: (offset = 0) =>
    request(`/production/recipes?offset=${offset}&limit=20`).then((v) =>
      list(v, recipe),
    ),
  productions: (offset = 0) =>
    request(`/production/batches?offset=${offset}&limit=20`).then((v) =>
      list(v, production),
    ),
  items: (kind: "raw" | "prepared", offset = 0) =>
    request(`/production/items?kind=${kind}&offset=${offset}&limit=100`).then(
      (v) => list(v, item),
    ),
  batches: (itemId: string, offset = 0) =>
    request(
      `/production/raw-batches?item_id=${encodeURIComponent(itemId)}&offset=${offset}&limit=100`,
    ).then((v) => list(v, rawBatch)),
  createRecipe: (body: RecipeInput, key: string) =>
    write("/recipes", body, key),
  produce: (body: ProductionInput, key: string) => write("/batches", body, key),
};
