import { afterEach, expect, it, vi } from "vitest";
import { identityApi } from "../src/shared/api/identity";

afterEach(() => vi.unstubAllGlobals());
it("отклоняет некорректный профиль и даты сессий", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ id: "missing-fields" })));
  vi.stubGlobal("fetch", fetchMock);
  await expect(identityApi.me()).rejects.toThrow(
    "Не удалось выполнить действие",
  );
  fetchMock.mockResolvedValue(
    new Response(
      JSON.stringify([
        {
          id: "id",
          current: true,
          created_at: "invalid",
          expires_at: "invalid",
        },
      ]),
    ),
  );
  await expect(identityApi.sessions()).rejects.toThrow(
    "Не удалось выполнить действие",
  );
});
it("связывает изменение с CSRF и проверяет контракт профиля", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ csrf_token: "synthetic-csrf" })),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: "id",
          login: "kitchen.01",
          phone: null,
          name: "Әлия",
          is_demo: true,
          roles: ["kitchen"],
          permissions: ["kitchen.read"],
        }),
      ),
    );
  vi.stubGlobal("fetch", fetchMock);
  const user = await identityApi.login("kitchen.01", "synthetic-password");
  expect(user.roles).toEqual(["kitchen"]);
  expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/v1/auth/login",
    expect.objectContaining({
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": "synthetic-csrf",
      },
    }),
  );
});
it("показывает русскую ошибку при невалидном ответе об ошибке", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(new Response("upstream failure", { status: 503 })),
  );
  await expect(identityApi.me()).rejects.toThrow(
    "Не удалось выполнить действие",
  );
});
