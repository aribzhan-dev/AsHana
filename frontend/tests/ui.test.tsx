import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Input, PhoneInput, Select } from "../src/shared/ui/Input";
import { Button } from "../src/shared/ui/Button";
import { CheckboxGroup } from "../src/shared/ui/CheckboxGroup";
import { QuantityInput } from "../src/shared/ui/QuantityInput";
import { quantityError } from "../src/shared/lib/quantity";
import { LoginForm } from "../src/features/identity/LoginForm";
import { ApiError, identityApi } from "../src/shared/api/identity";

it("ошибки и подсказки связаны с полем, placeholder не заменяет подпись", () => {
  render(
    <Input
      label="Логин"
      placeholder="Например, kassir.01"
      hint="Латинские буквы"
      error="Логин занят"
    />,
  );
  const field = screen.getByLabelText("Логин");
  expect(field).toHaveAttribute("aria-invalid", "true");
  expect(field).toHaveAccessibleDescription("Латинские буквы Логин занят");
  expect(screen.getByPlaceholderText("Например, kassir.01")).toBe(field);
});
it("телефон является необязательным контактным полем с placeholder", () => {
  render(<PhoneInput label="Телефон для связи" />);
  const field = screen.getByLabelText("Телефон для связи");
  expect(field).toHaveAttribute("placeholder", "700 000 00 00");
  expect(field).not.toBeRequired();
});
it("loading-кнопка блокирует повторное действие и не отправляет форму по умолчанию", async () => {
  const click = vi.fn();
  render(
    <Button loading onClick={click}>
      Сохранить
    </Button>,
  );
  const button = screen.getByRole("button", { name: "Сохранить" });
  await userEvent.click(button);
  expect(click).not.toHaveBeenCalled();
  expect(button).toHaveAttribute("aria-busy", "true");
  expect(button).toHaveAttribute("type", "button");
});
it("select и checkbox доступны по подписям и отражают выбор", async () => {
  function Form() {
    const [roles, setRoles] = useState<string[]>([]);
    return (
      <>
        <Select label="Тип">
          <option>Сотрудник</option>
          <option>Посетитель</option>
        </Select>
        <CheckboxGroup
          label="Роли"
          value={roles}
          onChange={setRoles}
          options={[{ value: "kitchen", label: "Кухня" }]}
        />
      </>
    );
  }
  render(<Form />);
  await userEvent.selectOptions(screen.getByLabelText("Тип"), "Посетитель");
  expect(screen.getByLabelText("Тип")).toHaveValue("Посетитель");
  await userEvent.click(screen.getByLabelText("Кухня"));
  expect(screen.getByLabelText("Кухня")).toBeChecked();
});
it("количество сохраняет редактирование и вставку; изменение ограничено диапазоном", async () => {
  function Quantity() {
    const [value, setValue] = useState("1");
    return (
      <QuantityInput
        label="Порции"
        value={value}
        onValueChange={setValue}
        min={1}
        max={2}
      />
    );
  }
  render(<Quantity />);
  expect(
    screen.getByRole("button", { name: "Уменьшить количество" }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Увеличить количество" }),
  );
  expect(screen.getByLabelText("Порции")).toHaveValue("2");
  expect(
    screen.getByRole("button", { name: "Увеличить количество" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Порции"), {
    target: { value: "1e3" },
  });
  expect(screen.getByLabelText("Порции")).toHaveValue("1e3");
  expect(quantityError("1e3")).toBeTruthy();
  for (const value of [
    "",
    "0",
    "-1",
    "1.2",
    "NaN",
    "Infinity",
    "два",
    "9007199254740993",
  ])
    expect(quantityError(value)).toBeTruthy();
  expect(quantityError("2")).toBeUndefined();
});
it("вход отправляет логин и сохраняет серверные ошибки поля", async () => {
  const login = vi
    .spyOn(identityApi, "login")
    .mockRejectedValue(
      new ApiError(422, "Проверьте данные", { login: ["Недопустимый логин"] }),
    );
  render(<LoginForm onLogin={vi.fn()} />);
  expect(screen.queryByLabelText("Телефон для связи")).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Логин"), "kassir.01");
  await userEvent.type(screen.getByLabelText("Пароль"), "synthetic-password");
  await userEvent.click(screen.getByRole("button", { name: "Войти" }));
  expect(login).toHaveBeenCalledWith("kassir.01", "synthetic-password");
  expect(await screen.findByText("Недопустимый логин")).toBeInTheDocument();
  expect(screen.getByLabelText("Логин")).toHaveAccessibleDescription(
    "Недопустимый логин",
  );
  login.mockRestore();
});

it("телефон сохраняет +7, принимает вставку номера и отклоняет буквы и лишние цифры", async () => {
  function Form() {
    const [phone, setPhone] = useState("");
    return (
      <>
        <PhoneInput
          label="Контакт"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        <output>{phone}</output>
      </>
    );
  }
  render(<Form />);
  const input = screen.getByLabelText("Контакт");
  fireEvent.change(input, { target: { value: "+7 (701) 000-00-11" } });
  expect(input).toHaveValue("7010000011");
  expect(screen.getByText("+77010000011")).toBeInTheDocument();
  fireEvent.change(input, { target: { value: "7010000011a" } });
  expect(input).toHaveValue("7010000011");
  expect(input).toHaveAttribute("aria-invalid", "true");
  fireEvent.change(input, { target: { value: "701000001122" } });
  expect(input).toHaveValue("7010000011");
  fireEvent.change(input, { target: { value: "" } });
  expect(input).toHaveValue("");
});
