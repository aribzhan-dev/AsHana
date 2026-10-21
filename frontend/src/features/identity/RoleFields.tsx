import { useEffect, useState } from "react";
import { identityApi, type RoleDefinition } from "../../shared/api/identity";
import { permissionLabels } from "../../shared/locales/permissions";
import type { Role } from "../../shared/api/identity";
import { identityRu as t } from "../../shared/locales/identity";
import { CheckboxGroup } from "../../shared/ui/CheckboxGroup";
export function RoleFields({
  value,
  onChange,
  disabled,
  error,
}: {
  value: Role[];
  onChange: (value: Role[]) => void;
  disabled?: boolean;
  error?: string;
}) {
  const [options, setOptions] = useState<RoleDefinition[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    void identityApi
      .listRoles()
      .then((data) => {
        if (alive) setOptions(data);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);
  return (
    <CheckboxGroup
      label={t.roles}
      value={value}
      onChange={onChange}
      disabled={disabled}
      error={error}
      options={options.map((role) => ({
        value: role.code,
        label: role.name,
        description:
          role.permissions.map((p) => permissionLabels[p] || p).join(" · ") ||
          "Только профиль",
      }))}
      hint={
        failed
          ? "Не удалось загрузить роли. Обновите страницу."
          : !options.length
            ? "Загрузка ролей…"
            : undefined
      }
    />
  );
}
