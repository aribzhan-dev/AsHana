import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import {
  CommissionEditor,
  ExpensesView,
  PlanEditor,
} from "../src/features/finance/MoneyViews";
import {
  basisPoints,
  financeApi,
  type FinanceDetails,
} from "../src/shared/api/finance";

const details: FinanceDetails = {
  expenses: [],
  payments: [],
  dividends: [],
  shifts: [],
  owners: [],
  plans: [],
  categories: {},
  daily: {},
  staff: [],
};

it("план продаж не принимает отрицательную сумму и сохраняет точные тиыны", async () => {
  const save = vi
    .spyOn(financeApi, "plan")
    .mockResolvedValue({ subject_id: "plan", version: 1 });
  const user = userEvent.setup();
  render(
    <PlanEditor
      month="2026-10"
      details={details}
      categories={[]}
      onChanged={vi.fn()}
    />,
  );
  const input = screen.getByLabelText("Цель на месяц, ₸");
  await user.click(input);
  await user.paste("-1500");
  expect(input).toHaveValue("");
  await user.type(input, "abc");
  expect(input).toHaveValue("");
  await user.paste("1500,25");
  await user.click(screen.getByRole("button", { name: "Сохранить план" }));
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({ target_minor: 150025 }),
    expect.any(String),
  );
});

it("расход отклоняет буквы, но сохраняет разрешённую отрицательную корректировку", async () => {
  const save = vi
    .spyOn(financeApi, "expense")
    .mockResolvedValue({ subject_id: "expense", version: 1 });
  const user = userEvent.setup();
  render(
    <ExpensesView
      details={details}
      categories={[
        {
          id: "rent",
          name: "Аренда",
          kind: "expense_category",
          commission_bp: 0,
          system: false,
        },
      ]}
      methods={[
        {
          id: "cash",
          name: "Наличные",
          kind: "payment_method",
          commission_bp: 0,
          system: false,
        },
      ]}
      onChanged={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Добавить расход" }));
  const input = screen.getByLabelText("Сумма, ₸");
  await user.type(input, "abc");
  expect(input).toHaveValue("");
  await user.type(input, "-25,50");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({ amount_minor: -2550 }),
    expect.any(String),
  );
});

it("комиссия отклоняет буквы, минус и вставку экспоненты, принимает запятую", async () => {
  const save = vi
    .spyOn(financeApi, "commission")
    .mockResolvedValue({ subject_id: "card", version: 1 });
  const user = userEvent.setup();
  render(
    <CommissionEditor
      methods={[
        {
          id: "card",
          name: "Карта",
          kind: "payment_method",
          commission_bp: 0,
          system: false,
        },
      ]}
      onChanged={vi.fn()}
    />,
  );
  const input = screen.getByLabelText("Карта, комиссия %");
  await user.type(input, "abc-+е");
  expect(input).toHaveValue("0");
  await user.clear(input);
  await user.paste("1e3");
  expect(input).toHaveValue("");
  await user.type(input, "1,25");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  expect(save).toHaveBeenCalledWith("card", 125, expect.any(String));
  fireEvent.change(input, { target: { value: "-5" } });
  expect(input).toHaveValue("1,25");
});

it("проценты не округляются молча и не принимают экспоненту или шестнадцатеричную запись", () => {
  for (const value of [
    "1e1",
    "0x10",
    "1.234",
    "-1",
    "100.01",
    "Infinity",
    "NaN",
    "abc",
  ])
    expect(basisPoints(value)).toBeUndefined();
  expect(basisPoints("1,25")).toBe(125);
  expect(basisPoints("100")).toBe(10000);
  expect(basisPoints("")).toBe(0);
});
