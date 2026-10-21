import { DetailsButton } from "../../shared/ui/DetailsButton";
import { displayText } from "../../shared/lib/display-text";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../shared/api/http";
import {
  productionApi,
  type Recipe,
  type Production,
} from "../../shared/api/production";
import { yieldLabel } from "../../shared/lib/production-validation";
import { errorMessage } from "../../shared/lib/forms";
import { stockDate, stockNumber } from "../../shared/lib/inventory-validation";
import { inventoryRu as s } from "../../shared/locales/inventory";
import { productionRu as t } from "../../shared/locales/production";
import { Button } from "../../shared/ui/Button";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Toast,
} from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { RecipeForm } from "./RecipeForm";
import { ProductionForm } from "./ProductionForm";

export function RecipeDetails({ recipe }: { recipe: Recipe }) {
  return (
    <div className="form-stack">
      <div className="production-facts">
        <div>
          <span>{t.expected}</span>
          <strong>
            {yieldLabel(recipe.expected_yield, recipe.output_unit)}
          </strong>
        </div>
        <div>
          <span>{t.portion}</span>
          <strong>
            {stockNumber(recipe.portion_quantity)}{" "}
            {s.units[recipe.portion_unit as "kg" | "l"]}
          </strong>
        </div>
      </div>
      <div>
        <p className="field-hint">{t.norm}</p>
        <ul className="production-lines">
          {recipe.lines.map((l) => (
            <li key={l.item_id}>
              <span>{l.item_name}</span>
              <strong>
                {stockNumber(l.quantity)} {s.units[l.unit as "kg" | "l"]}
              </strong>
            </li>
          ))}
        </ul>
      </div>
      <p>{displayText(recipe.instructions)}</p>
      <p className="field-hint">{stockDate(recipe.created_at)}</p>
    </div>
  );
}
type Editor =
  { kind: "recipe"; previous?: Recipe } | { kind: "produce"; recipe: Recipe };
export function ProductionBoard({ onExpired }: { onExpired: () => void }) {
  const [tab, setTab] = useState<"recipes" | "history">("recipes"),
    [offset, setOffset] = useState(0),
    [attempt, setAttempt] = useState(0);
  const [recipes, setRecipes] = useState<Recipe[]>([]),
    [productions, setProductions] = useState<Production[]>([]);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null),
    [busy, setBusy] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null),
    [detail, setDetail] = useState<Recipe | null>(null),
    [detailError, setDetailError] = useState(""),
    [detailAttempt, setDetailAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const pending =
      tab === "recipes"
        ? productionApi.recipes(offset).then((data) => {
            if (active) setRecipes(data);
          })
        : productionApi.productions(offset).then((data) => {
            if (active) setProductions(data);
          });
    void pending
      .catch((cause) => {
        if (active) {
          if (cause instanceof ApiError && cause.status === 401) onExpired();
          else setError(errorMessage(cause));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tab, offset, attempt, onExpired]);
  useEffect(() => {
    if (!detailId) return;
    let active = true;
    void productionApi
      .recipe(detailId)
      .then((data) => {
        if (active) setDetail(data);
      })
      .catch((cause) => {
        if (active) {
          if (cause instanceof ApiError && cause.status === 401) onExpired();
          else setDetailError(errorMessage(cause));
        }
      });
    return () => {
      active = false;
    };
  }, [detailId, detailAttempt, onExpired]);
  const refresh = useCallback(() => {
    setLoading(true);
    setError("");
    setAttempt((n) => n + 1);
  }, []);
  function saved(kind: "recipe" | "produce") {
    setEditor(null);
    setBusy(false);
    setToast(kind === "recipe" ? t.savedRecipe : t.savedProduction);
    setTab(kind === "recipe" ? "recipes" : "history");
    setOffset(0);
    refresh();
  }
  function changeTab(next: "recipes" | "history") {
    setTab(next);
    setOffset(0);
    refresh();
  }
  const count = tab === "recipes" ? recipes.length : productions.length;
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">{t.intro}</p>
        <h1>{t.title}</h1>
      </div>
      <div className="stock-tabs" aria-label={t.title}>
        <Button
          variant={tab === "recipes" ? "primary" : "secondary"}
          aria-pressed={tab === "recipes"}
          onClick={() => changeTab("recipes")}
        >
          {t.recipes}
        </Button>
        <Button
          variant={tab === "history" ? "primary" : "secondary"}
          aria-pressed={tab === "history"}
          onClick={() => changeTab("history")}
        >
          {t.history}
        </Button>
      </div>
      <div className="button-row">
        <Button icon="plus" onClick={() => setEditor({ kind: "recipe" })}>
          {t.newRecipe}
        </Button>
        <Button variant="secondary" disabled={loading} onClick={refresh}>
          {t.refresh}
        </Button>
      </div>
      {toast && <Toast onClose={() => setToast("")}>{toast}</Toast>}
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <>
          {!count && (
            <EmptyState
              title={tab === "recipes" ? t.noRecipes : t.noProductions}
            >
              <p>{t.setup}</p>
            </EmptyState>
          )}
          <div className="production-grid">
            {tab === "recipes"
              ? recipes.map((recipe) => (
                  <Card key={recipe.id} className="production-card">
                    <div className="production-card-heading">
                      <h2>{recipe.output_name}</h2>
                      <Badge>
                        {s.version} {recipe.version}
                      </Badge>
                    </div>
                    <p className="muted">
                      Выход:{" "}
                      {yieldLabel(recipe.expected_yield, recipe.output_unit)} ·
                      Ингредиентов: {recipe.lines.length}
                    </p>
                    <DetailsButton title={recipe.output_name}>
                      <RecipeDetails recipe={recipe} />
                    </DetailsButton>
                    <div className="button-row">
                      <Button
                        onClick={() => setEditor({ kind: "produce", recipe })}
                      >
                        {t.produce}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() =>
                          setEditor({ kind: "recipe", previous: recipe })
                        }
                      >
                        Редактировать рецепт
                      </Button>
                    </div>
                  </Card>
                ))
              : productions.map((p) => (
                  <Card key={p.id} className="production-card">
                    <div className="production-card-heading">
                      <h2>{p.output_name}</h2>
                      <Badge>
                        {s.version} {p.recipe_version}
                      </Badge>
                    </div>
                    <p className="muted">
                      {stockDate(p.created_at)} ·{" "}
                      {yieldLabel(p.actual_yield, p.output_unit)}
                    </p>
                    <DetailsButton title={p.output_name}>
                      <h3>{displayText(p.label)}</h3>
                      <p>{stockDate(p.created_at)}</p>
                      <div className="production-facts">
                        <div>
                          <span>{t.actual}</span>
                          <strong>
                            {yieldLabel(p.actual_yield, p.output_unit)}
                          </strong>
                        </div>
                        <div>
                          <span>{s.expires}</span>
                          <strong>{stockDate(p.expires_at)}</strong>
                        </div>
                      </div>
                      <h3>{t.consumption}</h3>
                      <ul className="production-lines">
                        {p.consumption.map((c) => (
                          <li key={c.batch_id}>
                            <span>
                              {c.item_name}
                              <small>{displayText(c.batch_label)}</small>
                            </span>
                            <strong>
                              {stockNumber(c.quantity)}{" "}
                              {s.units[c.unit as "kg" | "l"]}
                            </strong>
                          </li>
                        ))}
                      </ul>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setDetail(null);
                          setDetailError("");
                          setDetailId(p.recipe_id);
                        }}
                      >
                        {t.readRecipe}
                      </Button>
                      <p className="field-hint">
                        {s.author}: {p.actor_name || "Сотрудник"}
                      </p>
                    </DetailsButton>
                  </Card>
                ))}
          </div>
          <div className="stock-pagination">
            <Button
              variant="secondary"
              disabled={offset === 0}
              onClick={() => {
                setOffset((n) => Math.max(0, n - 20));
                refresh();
              }}
            >
              {s.previous}
            </Button>
            <span>
              {s.page} {offset / 20 + 1}
            </span>
            <Button
              variant="secondary"
              disabled={count < 20}
              onClick={() => {
                setOffset((n) => n + 20);
                refresh();
              }}
            >
              {s.next}
            </Button>
          </div>
        </>
      )}
      <p className="field-hint">{t.correction}</p>
      {editor && (
        <Dialog
          open
          title={
            editor.kind === "recipe"
              ? editor.previous
                ? t.newVersion
                : t.newRecipe
              : t.produce
          }
          onClose={() => {
            if (!busy) setEditor(null);
          }}
          busy={busy}
        >
          {editor.kind === "recipe" ? (
            <RecipeForm
              previous={editor.previous}
              onSaved={() => saved("recipe")}
              onExpired={onExpired}
              onBusy={setBusy}
            />
          ) : (
            <ProductionForm
              recipe={editor.recipe}
              onSaved={() => saved("produce")}
              onExpired={onExpired}
              onBusy={setBusy}
            />
          )}
        </Dialog>
      )}
      {detailId && (
        <Dialog
          open
          title={
            detail
              ? `${detail.output_name} · ${s.version} ${detail.version}`
              : t.readRecipe
          }
          onClose={() => setDetailId(null)}
        >
          {detail ? (
            <RecipeDetails recipe={detail} />
          ) : detailError ? (
            <ErrorState
              message={detailError}
              onRetry={() => {
                setDetailError("");
                setDetailAttempt((n) => n + 1);
              }}
            />
          ) : (
            <LoadingState />
          )}
        </Dialog>
      )}
    </>
  );
}
