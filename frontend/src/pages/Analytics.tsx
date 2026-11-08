import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/client';
import type { CategoryTotal, MonthTotal, Summary } from '../api/types';
import { Metric, PageHeading, State } from '../components/ui';
import { useAccounts } from '../lib/data';
import { isoDate, money, monthRange, monthTitle } from '../lib/format';
import { useLedger } from '../ledger';

const PERIODS = [0, -1, -2, -3, -4, -5];

export function AnalyticsPage() {
  const { base } = useLedger();
  const { data: accounts = [] } = useAccounts(true);
  const [offset, setOffset] = useState(0);
  const [chosenCurrency, setCurrency] = useState<string | null>(null);

  const currencies = [...new Set(accounts.map((account) => account.currency))];
  const currency = chosenCurrency ?? currencies[0] ?? 'RUB';
  const range = { ...monthRange(offset), currency };
  const now = new Date();
  const yearRange = { date_from: isoDate(new Date(now.getFullYear(), now.getMonth() - 11, 1)), date_to: isoDate(now), currency };

  const { data: summary } = useQuery({ queryKey: [base, 'summary', range], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: range }) });
  const { data: categories = [] } = useQuery({ queryKey: [base, 'by-category', range], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: range }) });
  const { data: months = [] } = useQuery({ queryKey: [base, 'monthly', yearRange], queryFn: () => api<MonthTotal[]>(`${base}/analytics/monthly`, { query: yearRange }) });

  const maxMonth = Math.max(...months.flatMap((m) => [Number(m.income), Number(m.expense)]), 1);
  const totalExpense = categories.reduce((sum, row) => sum + Number(row.total), 0);
  const income = Number(summary?.income ?? 0);
  const net = Number(summary?.net ?? 0);

  return (
    <div className="prototype-page">
      <PageHeading
        eyebrow="Аналитика"
        title="Динамика финансов"
        subtitle="Переводы между своими счетами не считаются доходом или расходом."
        action={
          <div className="row-actions">
            {currencies.length > 1 && (
              <select className="secondary-button" aria-label="Валюта" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {currencies.map((code) => <option key={code}>{code}</option>)}
              </select>
            )}
            <select className="secondary-button" aria-label="Месяц" value={offset} onChange={(e) => setOffset(Number(e.target.value))}>
              {PERIODS.map((value) => <option key={value} value={value}>{monthTitle(value)}</option>)}
            </select>
          </div>
        }
      />
      <div className="summary-strip">
        <Metric label="Доходы" value={money(summary?.income ?? 0, currency)} tone="good" />
        <Metric label="Расходы" value={money(summary?.expense ?? 0, currency)} tone="bad" />
        <Metric label="Сбережения" value={money(net, currency)} note={income > 0 ? `${Math.round((net / income) * 100)}% дохода` : undefined} tone={net >= 0 ? 'good' : 'bad'} />
      </div>
      <div className="analytics-grid">
        <section className="card chart-card">
          <div className="section-head">
            <div><h3>Доходы и расходы</h3><p>Последние 12 месяцев</p></div>
            <div className="chart-key"><span><i className="mint-bg" />Доходы</span><span><i className="coral-bg" />Расходы</span></div>
          </div>
          {months.length === 0 ? <State>Пока нет данных</State> : (
            <div className="bar-chart">
              {months.map((m) => (
                <div className="bar-pair" key={m.month} title={`${m.month}: доходы ${money(m.income, currency)}, расходы ${money(m.expense, currency)}`}>
                  <div>
                    <span style={{ height: `${(Number(m.income) / maxMonth) * 100}%` }} />
                    <span style={{ height: `${(Number(m.expense) / maxMonth) * 100}%` }} />
                  </div>
                  <small>{m.month.slice(5)}</small>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="card plain-card">
          <h3>Структура расходов</h3>
          <p>{monthTitle(offset)}</p>
          {categories.length === 0 && <State>Расходов нет</State>}
          {categories.map((row) => (
            <div className="progress-row" key={row.category_id}>
              <div><b>{row.category_name}</b><span>{money(row.total, currency)}</span></div>
              <div className="progress"><span style={{ width: `${(Number(row.total) / totalExpense) * 100}%` }} /></div>
              <small>{row.group_name} · {Math.round((Number(row.total) / totalExpense) * 100)}%</small>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
