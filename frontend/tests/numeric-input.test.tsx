import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { NumericInput } from "../src/shared/ui/NumericInput";

function Field({
  integer = false,
  signed = false,
}: {
  integer?: boolean;
  signed?: boolean;
}) {
  const [value, setValue] = useState("");
  return (
    <NumericInput
      label="Число"
      value={value}
      onValueChange={setValue}
      inputMode={integer ? "numeric" : "decimal"}
      allowNegative={signed}
    />
  );
}

it("денежное поле отклоняет недопустимую вставку целиком, не превращая минус в плюс", async () => {
  const user = userEvent.setup();
  render(<Field />);
  const input = screen.getByLabelText("Число");
  await user.click(input);
  for (const value of [
    "abc",
    "12abc",
    "-50",
    "+50",
    "1e3",
    "NaN",
    "Infinity",
    "1.2.3",
    "1,2.3",
  ]) {
    await user.paste(value);
    expect(input).toHaveValue("");
  }
  await user.paste("125,50");
  expect(input).toHaveValue("125,50");
  await user.clear(input);
  await user.type(input, "12.5");
  expect(input).toHaveValue("12.5");
});

it("целое количество не принимает дробь, позволяет выделять и заменять цифры", async () => {
  const user = userEvent.setup();
  render(<Field integer />);
  const input = screen.getByLabelText("Число");
  await user.click(input);
  await user.paste("1,5");
  expect(input).toHaveValue("");
  await user.type(input, "123");
  await user.keyboard("{Home}{Delete}4");
  expect(input).toHaveValue("423");
  await user.clear(input);
  expect(input).toHaveValue("");
});

it("отрицательная корректировка доступна только с явным разрешением", async () => {
  const user = userEvent.setup();
  render(<Field signed />);
  const input = screen.getByLabelText("Число");
  await user.type(input, "-12,50");
  expect(input).toHaveValue("-12,50");
  fireEvent.change(input, { target: { value: "--12" } });
  expect(input).toHaveValue("-12,50");
  await user.clear(input);
  await user.paste("-0.25");
  expect(input).toHaveValue("-0.25");
});

it("проверяет результат IME после окончания композиции", () => {
  render(<Field />);
  const input = screen.getByLabelText("Число");
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "中文" } });
  fireEvent.compositionEnd(input);
  expect(input).toHaveValue("");
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "12" } });
  fireEvent.compositionEnd(input);
  expect(input).toHaveValue("12");
});
