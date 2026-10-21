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
  return (
    <CheckboxGroup
      label={t.roles}
      value={value}
      onChange={onChange}
      disabled={disabled}
      error={error}
      options={(Object.keys(t.roleLabels) as Role[]).map((value) => ({
        value,
        label: t.roleLabels[value],
      }))}
    />
  );
}
