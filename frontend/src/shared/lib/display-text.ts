// Historical seed records stay immutable; only their presentation labels are simplified.
const initialLabels: Record<string, string> = {
  "Демо-поставка": "Начальная поставка",
  "Демонстрационная партия": "Начальная партия",
  "Демо-данные владельца, не фактическая поставка": "Начальное наполнение",
  "Демонстрационный рецепт: не утверждённая технологическая карта.":
    "Технологию приготовления необходимо заполнить.",
};
export function displayText(value: string): string {
  return initialLabels[value] || value;
}
