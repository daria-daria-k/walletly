import { useState } from 'react';
import { api, errorText } from '../api/client';
import type { ImportResult } from '../api/types';
import { ErrorNote, PageHeading } from '../components/ui';
import { useRefreshLedgerData } from '../lib/data';
import { useLedger } from '../ledger';

export function ImportPage() {
  const { base } = useLedger();
  const refresh = useRefreshLedgerData();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append('file', file);
    try {
      const response = await api<ImportResult>(`${base}/import`, { method: 'POST', form, query: { dry_run: dryRun } });
      setResult(response);
      if (!dryRun) await refresh();
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const ready = result?.dry_run && result.errors.length === 0 && result.created > 0;

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Данные" title="Импорт операций" subtitle="Загрузите Excel или CSV: сначала проверка, потом запись." />
      <section className="card plain-card">
        <h3>Файл</h3>
        <p className="columns-hint">
          Колонки: <b>Дата, Сумма, Счёт</b> — обязательные; Тип (доход / расход / перевод), Счёт зачисления, Категория, Описание. Названия счетов и категорий должны уже быть в Walletly. <a className="text-link" href="/import-template.csv" download>Скачать шаблон</a>
        </p>
        <input className="file-input" aria-label="Файл для импорта" type="file" accept=".xlsx,.csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null); }} />
        <div className="row-actions">
          <button className="secondary-button" disabled={!file || busy} onClick={() => send(true)}>Проверить файл</button>
          <button className="primary-button" disabled={!ready || busy} onClick={() => send(false)}>Загрузить</button>
        </div>
        <div style={{ marginTop: 14 }}><ErrorNote text={error} /></div>
        {result && result.errors.length === 0 && (
          <p className="form-ok">
            {result.dry_run ? `Проверено строк: ${result.total_rows}. Будет добавлено: ${result.created}.` : `Добавлено операций: ${result.created}.`}
            {result.skipped_duplicates > 0 && ` Уже есть в базе и пропущено: ${result.skipped_duplicates}.`}
          </p>
        )}
        {result && result.errors.length > 0 && (
          <>
            <ErrorNote text={`Ошибок: ${result.errors.length}. Файл не загружен — исправьте строки и проверьте снова.`} />
            <ul className="errors-list">
              {result.errors.slice(0, 100).map((item) => <li key={item.row}><b>Строка {item.row}:</b> {item.message}</li>)}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
