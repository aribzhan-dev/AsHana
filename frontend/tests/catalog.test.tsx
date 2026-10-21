import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  catalogApi,
  type Period,
  type MenuEntry,
} from "../src/shared/api/catalog";
import { ApiError } from "../src/shared/api/http";
import { PeriodForm, EntryForm } from "../src/features/catalog/CatalogForms";
import { WelcomePage } from "../src/pages/WelcomePage";
const period: Period = {
  id: "period",
  name: "Обед",
  starts_at: "2026-10-21T07:00:00Z",
  ends_at: "2026-10-21T09:00:00Z",
  published: false,
  version: 2,
  actor_id: "actor",
  created_at: "2026-10-21T00:00:00Z",
  updated_at: "2026-10-21T00:00:00Z",
};
const entry: MenuEntry = {
  id: "entry",
  period_id: "period",
  item_id: "juice",
  name: "Сок",
  description: "Яблочный",
  portion_label: "0,5 л",
  unit: "pcs",
  price_minor: 12345,
  published: true,
  version: 3,
  actor_id: "actor",
  created_at: period.created_at,
  updated_at: period.updated_at,
};
afterEach(() => vi.restoreAllMocks());
it("период требует правильного интервала и передаёт время Алматы в UTC с версией", async () => {
  const save = vi
    .spyOn(catalogApi, "savePeriod")
    .mockResolvedValue({ subject_id: "period", version: 3 });
  const saved = vi.fn();
  render(
    <PeriodForm
      previous={period}
      day="2026-10-21"
      onSaved={saved}
      onExpired={vi.fn()}
      onBusy={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Начало (Алматы)")).toHaveValue(
    "2026-10-21T12:00",
  );
  fireEvent.change(screen.getByLabelText("Окончание (Алматы)"), {
    target: { value: "2026-10-21T11:00" },
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить период" }),
  );
  expect(save).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Окончание (Алматы)")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  fireEvent.change(screen.getByLabelText("Окончание (Алматы)"), {
    target: { value: "2026-10-21T14:00" },
  });
  await userEvent.click(screen.getByLabelText("Опубликовать период"));
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить период" }),
  );
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(save).toHaveBeenCalledWith(
    "period",
    expect.objectContaining({
      expected_version: 2,
      starts_at: "2026-10-21T07:00:00.000Z",
      ends_at: "2026-10-21T09:00:00.000Z",
      published: true,
    }),
    expect.any(String),
  );
});
it("редактирование цены сохраняет тиыны, прежнюю версию и ключ после потери ответа", async () => {
  const save = vi
    .spyOn(catalogApi, "saveEntry")
    .mockRejectedValueOnce(new ApiError(0, "Потерян ответ"))
    .mockResolvedValueOnce({ subject_id: "entry", version: 4 });
  const saved = vi.fn();
  render(
    <EntryForm
      period={period}
      previous={entry}
      onSaved={saved}
      onExpired={vi.fn()}
      onBusy={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Цена, ₸")).toHaveValue("123.45");
  await userEvent.clear(screen.getByLabelText("Цена, ₸"));
  await userEvent.type(screen.getByLabelText("Цена, ₸"), "123,456");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить позицию" }),
  );
  expect(save).not.toHaveBeenCalled();
  await userEvent.clear(screen.getByLabelText("Цена, ₸"));
  await userEvent.type(screen.getByLabelText("Цена, ₸"), "123,45");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить позицию" }),
  );
  await screen.findByText(/Ответ не получен/);
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить позицию" }),
  );
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(save.mock.calls[0]?.[3]).toBe(save.mock.calls[1]?.[3]);
  expect(save.mock.calls[0]?.[2]).toEqual(
    expect.objectContaining({
      item_id: "juice",
      expected_version: 3,
      price_minor: 12345,
    }),
  );
});
it.each([
  { available: 0 },
  { available: 1.5 },
  { price_minor: 12.5 },
  { unit: "kg" },
])(
  "гостевое меню отклоняет повреждённую доступность и цену %j",
  async (bad) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            generated_at: period.created_at,
            currency: "KZT",
            entries: [
              {
                ...entry,
                period_name: "Обед",
                starts_at: period.starts_at,
                ends_at: period.ends_at,
                available: 8,
                ...bad,
              },
            ],
          }),
        ),
      ),
    );
    await expect(catalogApi.menu()).rejects.toThrow("Не удалось получить меню");
  },
);
it("обновление при возврате в окно убирает устаревшие данные при ошибке", async () => {
  const menu = vi
    .spyOn(catalogApi, "menu")
    .mockResolvedValueOnce({
      generated_at: period.created_at,
      currency: "KZT",
      entries: [
        {
          ...entry,
          period_name: "Обед",
          starts_at: period.starts_at,
          ends_at: period.ends_at,
          available: 8,
        },
      ],
    })
    .mockRejectedValueOnce(new ApiError(0, "Не удалось обновить меню"));
  render(<WelcomePage />);
  await screen.findByRole("heading", { name: "Сок" });
  fireEvent.focus(window);
  await screen.findByText("Не удалось обновить меню");
  expect(
    screen.queryByRole("heading", { name: "Сок" }),
  ).not.toBeInTheDocument();
  expect(menu).toHaveBeenCalledTimes(2);
});
