import { inventoryRu as t } from "../locales/inventory";
import { Button } from "./Button";
import { Icon } from "./Icon";

export function Pagination({
  page,
  hasNext,
  onPrevious,
  onNext,
}: {
  page: number;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <nav className="pagination" aria-label="Навигация по страницам">
      <Button
        variant="secondary"
        disabled={page <= 1}
        onClick={onPrevious}
        aria-label={t.previous}
        title={t.previous}
      >
        <Icon name="arrow-left" />
        <span className="pagination-label">{t.previous}</span>
      </Button>
      <span className="pagination-page" aria-live="polite" aria-atomic="true">
        {t.page} {page}
      </span>
      <Button
        variant="secondary"
        disabled={!hasNext}
        onClick={onNext}
        aria-label={t.next}
        title={t.next}
      >
        <span className="pagination-label">{t.next}</span>
        <Icon name="arrow-left" className="pagination-next-icon" />
      </Button>
    </nav>
  );
}
