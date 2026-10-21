// Historical seed records stay immutable; only their presentation labels are simplified.
const initialLabels: Record<string, string> = {
  "Демо-поставка": "Начальная поставка",
  "Демонстрационная партия": "Начальная партия",
  "Демо-данные владельца, не фактическая поставка": "Начальное наполнение",
  "Демонстрационный рецепт: не утверждённая технологическая карта.":
    "Технологию приготовления необходимо заполнить.",
};
export function displayText(value: string): string {
  if (initialLabels[value]) return initialLabels[value];
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  if (new RegExp(`^Кассовая продажа (?:ДЕМО )?${uuid}$`, "i").test(value))
    return "Продажа на кассе";
  if (new RegExp(`^Выпуск ${uuid}$`, "i").test(value))
    return "Собственное производство";
  if (new RegExp(`^Выдача (?:ДЕМО )?${uuid}$`, "i").test(value))
    return "Выдача заказа";
  return value;
}
