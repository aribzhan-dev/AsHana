import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  nameError,
  loginError,
  passwordError,
  phoneError,
} from "../src/shared/lib/identity-validation";
import { Input } from "../src/shared/ui/Input";

describe("Проверки данных сотрудника", () => {
  it("принимает только мобильные номера Казахстана", () => {
    expect(phoneError("+7 (701) 000-00-01")).toBeUndefined();
    for (const phone of [
      "+79001234567",
      "+77271234567",
      "87010000001",
      "+77010000001\n",
      "+77010000001abc",
    ])
      expect(phoneError(phone)).toBeTruthy();
  });
  it("поддерживает казахские имена и не изменяет пароль", () => {
    expect(nameError("Нұр-Сұлтан")).toBeUndefined();
    expect(nameError("О’Коннор")).toBeUndefined();
    expect(nameError("A\n")).toBeTruthy();
    expect(nameError("Анна2")).toBeTruthy();
    expect(passwordError(" ".repeat(12))).toBeUndefined();
    expect(passwordError("короткий")).toBeTruthy();
  });
  it("переключает видимость без отправки формы и потери значения", async () => {
    const user = userEvent.setup();
    render(
      <Input
        type="password"
        label="Пароль"
        defaultValue="  пример пароля  "
        autoComplete="new-password"
      />,
    );
    const input = screen.getByLabelText("Пароль");
    expect(input).toHaveAttribute("type", "password");
    const toggle = screen.getByRole("button", { name: "Показать пароль" });
    expect(toggle).toHaveAttribute("type", "button");
    await user.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveValue("  пример пароля  ");
    expect(
      screen.getByRole("button", { name: "Скрыть пароль" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});

it("логин не зависит от телефона и проверяется до отправки", () => {
  expect(loginError(" Kassir.01 ")).toBeUndefined();
  for (const value of [
    "+77010000001",
    "админ",
    "1admin",
    "ab",
    "admin\n",
    "Kaa",
  ])
    expect(loginError(value)).toBeTruthy();
});
