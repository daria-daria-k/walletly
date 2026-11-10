import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { useState } from 'react';
import { api } from '../api/client';
import type { CategoryTotal, MonthTotal, Summary } from '../api/types';
import { StyledSelect } from '../components/StyledSelect';
import { Metric, PageHeading, State } from '../components/ui';
import { useAccounts, useCategoryGroups } from '../lib/data';
import { capitalize, changePercent, isoDate, money, monthDative, monthRange, monthTitle, samePeriodRange, signedPercent } from '../lib/format';
import { CategoryIcon } from '../components/CategoryIcon';
import { useLedger } from '../ledger';

const PERIODS = [0, -1, -2, -3, -4, -5];

export function AnalyticsPage() {
  const { base } = useLedger();
  const { data: accounts = [] } = useAccounts(true);
  const { data: groups = [] } = useCategoryGroups();
  const [offset, setOffset] = useState(0);
  const [chosenCurrency, setCurrency] = useState<string | null>(null);

  const currencies = [...new Set(accounts.map((account) => account.currency))];
  const currency = chosenCurrency ?? currencies[0] ?? 'RUB';
  const isCurrent = offset === 0;
  const range = { ...monthRange(offset), currency };
  // Текущий месяц неполный: сравниваем его с теми же днями прошлого, а полный — с полным
  const previous = { ...(isCurrent ? samePeriodRange() : monthRange(offset - 1)), currency };
  const now = new Date();
  const yearRange = { date_from: isoDate(new Date(now.getFullYear(), now.getMonth() - 11, 1)), date_to: isoDate(now), currency };

  const { data: summary } = useQuery({ queryKey: [base, 'summary', range], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: range }) });
  const { data: prior } = useQuery({ queryKey: [base, 'summary', previous], queryFn: () => api<Summary>(`${base}/analytics/summary`, { query: previous }) });
  const { data: categories = [] } = useQuery({ queryKey: [base, 'by-category', range], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: range }) });
  const { data: priorCategories = [] } = useQuery({ queryKey: [base, 'by-category', previous], queryFn: () => api<CategoryTotal[]>(`${base}/analytics/by-category`, { query: previous }) });
  const { data: months = [] } = useQuery({ queryKey: [base, 'monthly', yearRange], queryFn: () => api<MonthTotal[]>(`${base}/analytics/monthly`, { query: yearRange }) });

  const balance = accounts.filter((a) => a.is_active && a.currency === currency).reduce((sum, a) => sum + Number(a.balance), 0);
  const maxMonth = Math.max(...months.flatMap((m) => [Number(m.income), Number(m.expense)]), 1);
  const income = Number(summary?.income ?? 0);
  const expense = Number(summary?.expense ?? 0);
  const net = income - expense;
  const incomeChange = changePercent(income, Number(prior?.income ?? 0));
  const expenseChange = changePercent(expense, Number(prior?.expense ?? 0));

  const dayOfMonth = now.getDate();
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  // Простая экстраполяция: оставшиеся дни тратим в том же темпе. Модель прогноза — на этапе ML
  const forecastExpense = (expense / dayOfMonth) * daysInMonth;
  const remainingSpend = forecastExpense - expense;
  const forecastBalance = balance - remainingSpend;
  const forecastNet = income - forecastExpense;
  const monthProgress = Math.round((dayOfMonth / daysInMonth) * 100);

  const before = new Map(priorCategories.map((row) => [row.category_id, Number(row.total)]));
  const categoryIcon = new Map(groups.flatMap((group) => group.categories.map((category) => [category.id, category.icon_key] as const)));
  const trends = categories
    .filter((row) => (before.get(row.category_id) ?? 0) > 0)
    .map((row) => {
      const was = before.get(row.category_id)!;
      return { id: row.category_id, name: row.category_name, diff: Number(row.total) - was, percent: Math.round(((Number(row.total) - was) / was) * 100) };
    })
    .filter((item) => item.diff !== 0)
    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))
    .slice(0, 3);

  const compareTitle = isCurrent ? `${capitalize(monthTitle().split(' ')[0])} по сравнению с теми же днями прошлого месяца` : `${capitalize(monthTitle(offset).split(' ')[0])} по сравнению с предыдущим месяцем`;
  const compareTo = `к ${monthDative(offset - 1)}`;

  return (
    <div className="prototype-page">
      <PageHeading
        eyebrow="Аналитика"
        title="Динамика финансов"
        subtitle="Сравнивайте периоды и находите точки роста."
        action={
          <div className="row-actions">
            {currencies.length > 1 && (
              <StyledSelect ariaLabel="Валюта" value={currency} onChange={setCurrency} options={currencies.map((code) => ({ value: code, label: code }))} />
            )}
            <StyledSelect ariaLabel="Период аналитики" value={String(offset)} onChange={(value) => setOffset(Number(value))} options={PERIODS.map((value) => ({ value: String(value), label: capitalize(monthTitle(value)) }))} />
          </div>
        }
      />
      <div className="summary-strip four">
        <Metric label="Доходы" value={money(income, currency)} note={incomeChange !== null ? `${signedPercent(incomeChange)} ${compareTo}` : undefined} tone="good" />
        <Metric label="Расходы" value={money(expense, currency)} note={expenseChange !== null ? `${signedPercent(expenseChange)} ${compareTo}` : undefined} />
        <Metric label="Сбережения" value={money(net, currency)} note={income > 0 ? `${Math.round((net / income) * 100)}% дохода` : undefined} />
        {isCurrent
          ? <Metric label="Прогноз остатка" value={money(forecastBalance, currency)} note={`на ${daysInMonth} число`} />
          : <Metric label="Текущий остаток" value={money(balance, currency)} note="на всех счетах" />}
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
                  <small>{new Date(`${m.month}-01T00:00:00`).toLocaleDateString('ru-RU', { month: 'narrow' })}</small>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="card insight-panel">
          <span className="insight-icon"><Sparkles /></span>
          <p className="eyebrow">Прогноз</p>
          {isCurrent ? (
            <>
              <h3>{forecastNet >= 0 ? 'Вы завершите месяц в плюсе' : 'Расходы могут превысить доходы'}</h3>
              <p>При текущем темпе расходов {forecastNet >= 0 ? 'свободный остаток' : 'перерасход'} составит около <b>{money(Math.abs(Math.round(forecastNet)), currency)}</b>.</p>
              <div className="confidence"><span>Прошло месяца</span><b>{monthProgress}%</b></div>
              <div className="progress"><span style={{ width: `${monthProgress}%` }} /></div>
            </>
          ) : (
            <>
              <h3>Месяц завершён</h3>
              <p>Итог месяца: <b>{money(net, currency)}</b>. Прогноз строится только для текущего месяца.</p>
            </>
          )}
        </section>
      </div>
      <section className="card trend-card">
        <div className="section-head"><div><h3>Что изменилось</h3><p>{compareTitle}</p></div></div>
        {trends.length === 0 ? <State>Пока не с чем сравнивать</State> : (
          <div className="trend-list">
            {trends.map((item) => (
              <div className="trend-item" key={item.id}>
                <div className="trend-icon"><CategoryIcon name={item.name} iconKey={categoryIcon.get(item.id)} /></div>
                <div><b>{item.name}</b><span>{item.diff < 0 ? 'Экономия' : 'Рост на'} {money(Math.abs(item.diff), currency)}</span></div>
                <strong className={item.diff < 0 ? 'good' : ''}>{signedPercent(item.percent)}</strong>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
