import { useQuery } from '@tanstack/react-query';
import { BadgeCheck, Check, Download, FileSpreadsheet, FileText, Upload } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { api, downloadFile, errorText } from '../api/client';
import type { ImportBatch, ImportResult } from '../api/types';
import { StyledSelect } from '../components/StyledSelect';
import { ErrorNote, PageHeading, State } from '../components/ui';
import { useRefreshLedgerData } from '../lib/data';
import { capitalize, dateTime, isoDate, monthRange, monthTitle, plural } from '../lib/format';
import { useLedger } from '../ledger';

const operations = (count: number) => plural(count, 'операция', 'операции', 'операций');

function periodRange(period: string): { date_from?: string; date_to?: string } {
  if (period === 'all') return {};
  if (period === 'year') {
    const now = new Date();
    return { date_from: isoDate(new Date(now.getFullYear(), 0, 1)), date_to: isoDate(now) };
  }
  return monthRange(Number(period));
}

function HistoryRow({ batch }: { batch: ImportBatch }) {
  return (
    <div className="history-row">
      <span className="file-icon"><FileSpreadsheet size={18} /></span>
      <div><b>{batch.filename}</b><small>{dateTime(batch.created_at)}</small></div>
      <span>{operations(batch.created)}</span>
      <em className={batch.errors ? 'warning' : ''}>{batch.errors ? plural(batch.errors, 'ошибка', 'ошибки', 'ошибок') : 'Готово'}</em>
    </div>
  );
}

export function ImportPage() {
  const { base } = useLedger();
  const refresh = useRefreshLedgerData();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [period, setPeriod] = useState('0');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const { data: history = [], refetch: refetchHistory } = useQuery({
    queryKey: [base, 'import-history'],
    queryFn: () => api<ImportBatch[]>(`${base}/import/history`),
  });

  async function send(target: File, dryRun: boolean) {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append('file', target);
    try {
      const response = await api<ImportResult>(`${base}/import`, { method: 'POST', form, query: { dry_run: dryRun } });
      setResult(response);
      if (!dryRun) await refresh();
      await refetchHistory();
    } catch (err) {
      setResult(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function choose(target: File | undefined) {
    if (!target) return;
    setFile(target);
    setResult(null);
    // Сразу проверяем: запись в базу произойдёт только по кнопке «Продолжить»
    send(target, true);
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }

  async function exportReport() {
    setExporting(true);
    setExportError(null);
    try {
      await downloadFile(`${base}/export`, 'walletly-export.xlsx', periodRange(period));
    } catch (err) {
      setExportError(errorText(err));
    } finally {
      setExporting(false);
    }
  }

  const periods = [
    ...[0, -1, -2].map((offset) => ({ value: String(offset), label: capitalize(monthTitle(offset)) })),
    { value: 'year', label: `${new Date().getFullYear()} год` },
    { value: 'all', label: 'Всё время' },
  ];
  const ready = result?.dry_run && result.errors.length === 0 && result.created > 0;

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Данные" title="Импорт и экспорт" subtitle="Переносите операции из банковских выписок и сохраняйте отчёты." />
      <div className="import-grid">
        <section className="card import-panel">
          <div className="section-icon"><Upload /></div>
          <h3>Импорт операций</h3>
          <p>Загрузите Excel или CSV. Сначала Walletly проверит файл, и только потом добавит операции.</p>
          <input ref={inputRef} hidden aria-label="Файл для импорта" type="file" accept=".xlsx,.csv" onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ''; }} />
          <button
            className={`upload-zone ${dragging ? 'dragging' : ''}`}
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
          >
            <FileSpreadsheet />
            <b>{busy ? 'Обрабатываем файл…' : file ? file.name : 'Перетащите файл или нажмите для выбора'}</b>
            <span>{file ? `${Math.ceil(file.size / 1024)} КБ` : 'XLSX или CSV до 5 МБ'}</span>
          </button>
          <p className="columns-hint">
            Колонки: <b>Дата, Сумма, Счёт</b> — обязательные; Тип, Счёт зачисления, Категория, Описание. Счета и категории должны уже быть в Walletly. <a className="text-link" href="/import-template.csv" download>Скачать шаблон</a>
          </p>
          <div style={{ marginTop: 14 }}><ErrorNote text={error} /></div>
          {result && result.errors.length === 0 && (
            <div className="import-success">
              <BadgeCheck />
              <div>
                {ready && <b>Файл успешно распознан</b>}
                {!result.dry_run && <b>Импорт завершён</b>}
                {result.dry_run && !ready && <b>Новых операций нет</b>}
                <span>
                  {result.dry_run ? (ready ? `${operations(result.created)} к добавлению` : 'Все строки уже есть в Walletly') : `Добавлено: ${operations(result.created)}`}
                  {result.skipped_duplicates > 0 && ` · уже в базе: ${result.skipped_duplicates}`}
                </span>
              </div>
              {ready && file && <button className="primary-button" disabled={busy} onClick={() => send(file, false)}>Продолжить</button>}
            </div>
          )}
          {result && result.errors.length > 0 && (
            <>
              <ErrorNote text={`Ошибок: ${result.errors.length}. Файл не загружен: исправьте строки и выберите его снова.`} />
              <ul className="errors-list">
                {result.errors.slice(0, 100).map((item) => <li key={item.row}><b>Строка {item.row}:</b> {item.message}</li>)}
              </ul>
            </>
          )}
        </section>
        <section className="card export-panel">
          <div className="section-icon"><Download /></div>
          <h3>Экспорт отчёта</h3>
          <p>Выберите формат и период для выгрузки.</p>
          <label>Период<StyledSelect ariaLabel="Период экспорта" value={period} onChange={setPeriod} options={periods} /></label>
          <div className="format-cards">
            <button className="selected" aria-pressed="true"><FileSpreadsheet /><span><b>Excel</b><small>Операции и сводка</small></span><Check /></button>
            <button disabled title="Появится позже"><FileText /><span><b>PDF</b><small>Появится позже</small></span></button>
          </div>
          <ErrorNote text={exportError} />
          <button className="primary-button wide-button" disabled={exporting} onClick={exportReport}><Download size={17} />{exporting ? 'Готовим файл…' : 'Скачать отчёт'}</button>
        </section>
      </div>
      <section className="card import-history">
        <div className="section-head"><div><h3>История импорта</h3><p>Последние обработанные файлы</p></div></div>
        {history.length === 0 ? <State>Файлы ещё не загружались</State> : history.map((batch) => <HistoryRow key={batch.id} batch={batch} />)}
      </section>
    </div>
  );
}
