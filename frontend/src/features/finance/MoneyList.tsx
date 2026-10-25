import { shortMoney, stockDate } from "../../shared/lib/inventory-validation";

export function MoneyList({
  rows,
}: {
  rows: {
    id: string;
    label: string;
    amount_minor: number;
    at: string;
    method_name: string;
    note: string;
  }[];
}) {
  if (!rows.length) return <p className="muted">Записей пока нет.</p>;
  return (
    <div className="table-wrap">
      <table className="report-table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                {r.label}
                {r.note && <small className="muted">{r.note}</small>}
              </td>
              <td>{stockDate(r.at)}</td>
              <td>{r.method_name}</td>
              <td className={`num ${r.amount_minor < 0 ? "debt" : ""}`}>
                {shortMoney(r.amount_minor)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
