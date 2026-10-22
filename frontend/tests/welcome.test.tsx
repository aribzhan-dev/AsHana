import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WelcomePage } from "../src/pages/WelcomePage";
import { ThemeSelect } from "../src/shared/ui/ThemeSelect";
import { checkReadiness } from "../src/shared/api/health";

describe("Стартовый экран", () => {
  it("показывает загрузку, отказ и успешный повтор", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("private connection details"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            generated_at: "2026-10-21T07:00:00Z",
            currency: "KZT",
            entries: [],
          }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(<WelcomePage />);
    expect(await screen.findByText(/Не удалось связаться/)).toBeInTheDocument();
    expect(screen.queryByText(/private connection/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(
      await screen.findByText("Сейчас нет доступных блюд"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Закажи заранее и забери без очереди"),
    ).toBeInTheDocument();
  });

  it.each([
    new Response("upstream unavailable", { status: 503 }),
    new Response("<html>not json</html>"),
    new Response(JSON.stringify({ status: "ok", service: "another-service" })),
  ])("отклоняет ошибку или неверный ответ API", async (response) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    expect(await checkReadiness(new AbortController().signal)).toBe(false);
  });
});

describe("Темы", () => {
  it("сохраняет выбор и восстанавливает после повторного открытия", async () => {
    const first = render(<ThemeSelect />);
    await userEvent.click(
      screen.getByRole("button", { name: /Тема оформления:/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Тёмная" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("ashana-theme")).toBe("dark");
    first.unmount();
    render(<ThemeSelect />);
    expect(
      screen.getByRole("button", { name: "Тема оформления: Тёмная" }),
    ).toBeInTheDocument();
  });

  it("работает при недоступном хранилище", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error();
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error();
    });
    render(<ThemeSelect />);
    await userEvent.click(
      screen.getByRole("button", { name: /Тема оформления:/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Тёмная" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
