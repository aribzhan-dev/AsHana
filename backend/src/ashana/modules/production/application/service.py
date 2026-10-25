import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ashana.modules.inventory.domain.models import Batch, Item, Movement, change_quantity, quantity
from ashana.modules.production.application.ports import ProductionUnitOfWork
from ashana.modules.production.domain.models import (
    Consumption,
    ConsumptionInput,
    IngredientInput,
    Production,
    Recipe,
    RecipeLine,
    portion_size,
    whole_yield,
)
from ashana.shared.domain import BusinessError, Result, invalid, text_value


class ProductionService:
    def __init__(
        self,
        uow: Callable[[], ProductionUnitOfWork],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.uow, self.clock = uow, clock

    def recipe(self, token: str, recipe_id: UUID) -> Recipe:
        with self.uow() as uow:
            uow.authorize(token)
            recipe = uow.repository.recipe(recipe_id)
            if not recipe:
                raise BusinessError("NOT_FOUND", "Версия рецепта не найдена")
            return recipe

    def recipes(self, token: str, offset: int = 0, limit: int = 20) -> list[Recipe]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.recipes(offset, limit)

    def productions(self, token: str, offset: int = 0, limit: int = 20) -> list[Production]:
        with self.uow() as uow:
            uow.authorize(token)
            return uow.repository.productions(offset, limit)

    def items(self, token: str, kind: str, offset: int = 0, limit: int = 100) -> list[Item]:
        with self.uow() as uow:
            uow.authorize(token)
            if kind not in ("raw", "prepared"):
                raise invalid("kind", "Выберите сырьё или собственную продукцию")
            return uow.stock.items(offset, limit, kind=kind)

    def batches(self, token: str, item_id: UUID, offset: int = 0, limit: int = 100) -> list[Batch]:
        with self.uow() as uow:
            uow.authorize(token)
            item = uow.stock.item(item_id)
            if not item or item.kind != "raw":
                raise invalid("item_id", "Выберите сырьё для производства")
            return uow.stock.batches(offset, limit, item_id=item_id)

    def _write(
        self,
        token: str,
        operation: str,
        key: UUID,
        payload: dict[str, object],
        action: Callable[[ProductionUnitOfWork, UUID], Result],
    ) -> Result:
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        with self.uow() as uow:
            actor = uow.authorize(token)
            replay = uow.stock.replay(actor, operation, key, fingerprint)
            if replay:
                return replay
            result = action(uow, actor)
            now = self.clock()
            uow.stock.audit(actor, operation, result.subject_id, now)
            uow.stock.remember(actor, operation, key, fingerprint, result, now)
            uow.commit()
            return result

    def create_recipe(
        self,
        token: str,
        key: UUID,
        output_item_id: UUID,
        previous_version: int,
        expected_yield: int,
        portion_quantity: str,
        portion_unit: str,
        instructions: str,
        lines: list[IngredientInput],
    ) -> Result:
        def action(uow: ProductionUnitOfWork, actor: UUID) -> Result:
            output = uow.stock.item(output_item_id)
            if not output or output.kind != "prepared":
                raise invalid("output_item_id", "Выберите собственную продукцию со склада")
            current = uow.repository.lock_recipe(output.id)
            if current != previous_version:
                raise BusinessError("STALE_RECIPE", "Рецепт изменился. Обновите список версий")
            if not 1 <= len(lines) <= 30 or len({line.item_id for line in lines}) != len(lines):
                raise invalid("lines", "Укажите от 1 до 30 разных ингредиентов")
            normalized = []
            for line in lines:
                item = uow.stock.item(line.item_id)
                if not item or item.kind != "raw":
                    raise invalid("lines", "В рецепте разрешено только сырьё")
                normalized.append(
                    RecipeLine(item.id, quantity(line.quantity, line.unit, item.unit), item.unit)
                )
            size, base = portion_size(portion_quantity, portion_unit)
            recipe = Recipe(
                uuid4(),
                output.id,
                current + 1,
                whole_yield(expected_yield),
                size,
                base,
                text_value(instructions, "instructions", 2000),
                actor,
                self.clock(),
                tuple(normalized),
            )
            uow.repository.add_recipe(recipe)
            return Result(recipe.id, recipe.version)

        return self._write(
            token,
            "recipe_created",
            key,
            {
                "output_item_id": output_item_id,
                "previous_version": previous_version,
                "expected_yield": expected_yield,
                "portion_quantity": portion_quantity,
                "portion_unit": portion_unit,
                "instructions": instructions,
                "lines": [asdict(line) for line in lines],
            },
            action,
        )

    def produce(
        self,
        token: str,
        key: UUID,
        recipe_id: UUID,
        label: str,
        actual_yield: int,
        expires_at: datetime,
        suitability_confirmed: bool,
        consumption: list[ConsumptionInput],
    ) -> Result:
        def action(uow: ProductionUnitOfWork, actor: UUID) -> Result:
            recipe = uow.repository.recipe(recipe_id)
            if not recipe:
                raise BusinessError("NOT_FOUND", "Версия рецепта не найдена")
            if suitability_confirmed is not True:
                raise invalid("suitability_confirmed", "Подтвердите пригодность выбранного сырья")
            count = whole_yield(actual_yield)
            batch_label = text_value(label, "label", 100)
            if not 1 <= len(consumption) <= 100 or len({c.batch_id for c in consumption}) != len(
                consumption
            ):
                raise invalid("consumption", "Укажите от 1 до 100 разных партий сырья")
            locked = []
            for entry in sorted(consumption, key=lambda c: c.batch_id):
                batch = uow.stock.batch(entry.batch_id, lock=True)
                if not batch:
                    raise BusinessError("NOT_FOUND", "Партия сырья не найдена")
                locked.append((entry, batch))
            # Evaluate expiry after waiting for every row lock, not at request arrival.
            now = self.clock()
            if not expires_at.tzinfo or expires_at <= now:
                raise invalid("expires_at", "Срок готового продукта должен быть позже выпуска")
            if {batch.item_id for _, batch in locked} != {line.item_id for line in recipe.lines}:
                raise invalid("consumption", "Укажите все ингредиенты рецепта без лишних позиций")
            production_id = uuid4()
            reason = f"Выпуск {production_id}"
            actual = []
            for entry, batch in locked:
                amount = quantity(entry.quantity, entry.unit, batch.unit)
                if batch.available_at(now) < amount:
                    raise BusinessError(
                        "INSUFFICIENT_STOCK",
                        f"Недостаточно пригодного сырья: {batch.item_name}, {batch.label}",
                    )
                updated = change_quantity(batch, -amount)
                movement_id = uuid4()
                uow.stock.save_batch(updated)
                uow.stock.add_movement(
                    Movement(
                        movement_id,
                        batch.id,
                        "production_consume",
                        -amount,
                        batch.on_hand,
                        updated.on_hand,
                        reason,
                        actor,
                        now,
                        updated.version,
                        batch.status,
                        updated.status,
                    )
                )
                actual.append(Consumption(batch.id, amount, batch.unit, movement_id, batch.item_id))
            output = Batch(
                production_id,
                recipe.output_item_id,
                batch_label,
                Decimal(count),
                Decimal(0),
                "active",
                1,
                0,
                now,
                expires_at,
                reason,
                actor,
                now,
                recipe.output_unit,
            )
            uow.stock.add_batch(output)
            uow.stock.add_movement(
                Movement(
                    uuid4(),
                    output.id,
                    "production_output",
                    Decimal(count),
                    Decimal(0),
                    Decimal(count),
                    reason,
                    actor,
                    now,
                    1,
                    "active",
                    "active",
                )
            )
            uow.repository.add_production(
                Production(
                    production_id,
                    recipe.id,
                    count,
                    actor,
                    now,
                    tuple(actual),
                )
            )
            return Result(production_id, 1)

        return self._write(
            token,
            "production_confirmed",
            key,
            {
                "recipe_id": recipe_id,
                "label": label,
                "actual_yield": actual_yield,
                "expires_at": expires_at,
                "suitability_confirmed": suitability_confirmed,
                "consumption": [asdict(c) for c in consumption],
            },
            action,
        )
