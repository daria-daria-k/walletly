import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, BadgeCheck, Check, ChevronRight, Gauge, RefreshCw, Sparkles, WandSparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { api } from '../api/client';
import type { Insights } from '../api/types';
import { ErrorState, LoadingState, PageHeading } from '../components/ui';
import { money, monthTitle } from '../lib/format';
import { useLedger } from '../ledger';

function InsightCard({ tone, icon, label, title, text, action, onAction }: { tone: string; icon: ReactNode; label: string; title: string; text: string; action: string; onAction: () => void }) {
  return (
    <section className={`card ai-insight ${tone}`}>
      <span>{icon}</span>
      <small>{label}</small>
      <h3>{title}</h3>
      <p>{text}</p>
      <button onClick={onAction}>{action}<ChevronRight /></button>
    </section>
  );
}

export function AiPage() {
  const { base } = useLedger();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: [base, 'insights'],
    queryFn: () => api<Insights>(`${base}/analytics/insights`),
  });

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  const { forecast, anomaly, overspend, limits, plan } = data;
  const change = forecast.change_percent;
  const ring = forecast.method === 'ml' ? forecast.accuracy_percent ?? 0 : forecast.month_progress;
  const compare = change === null
    ? 'Сравнение появится, когда накопится история за прошлые месяцы.'
    : `Это на ${Math.abs(change)}% ${change >= 0 ? 'больше' : 'меньше'}, чем в среднем за прошлые месяцы.`;
  const growth = overspend ? ` Основной рост в категории «${overspend.category_name}».` : '';

  const limitTitle = limits.total === 0
    ? 'Лимиты не заданы'
    : limits.over > 0
      ? `Лимит превышен в категориях: ${limits.over}`
      : limits.near > 0
        ? `Близко к лимиту: ${limits.near}`
        : 'Лимиты в норме';

  return (
    <div className="prototype-page">
      <PageHeading eyebrow="Walletly AI" title="Умная аналитика" subtitle="Прогнозы, необычные траты и рекомендации на основе ваших операций." action={<button className="secondary-button" disabled={isFetching} onClick={() => refetch()}><RefreshCw size={16} />Обновить анализ</button>} />
      <section className="ai-hero">
        <div>
          <span className="ai-orb"><WandSparkles /></span>
          <p>Прогноз на {monthTitle().split(' ')[0]}</p>
          <h2>Расходы составят около {money(Math.round(Number(forecast.projected)))}</h2>
          <span>{compare}{growth}</span>
        </div>
        {/* Точность измерена на прошлых месяцах. Без модели показываем только, сколько месяца позади */}
        <div className="forecast-ring" style={{ background: `conic-gradient(#fff 0 ${ring}%,#ffffff25 ${ring}%)` }}>
          {forecast.method === 'ml' ? <div><b>{forecast.accuracy_percent}%</b><span>точность</span></div> : <div><b>{forecast.month_progress}%</b><span>месяца прошло</span></div>}
        </div>
      </section>
      <div className="ai-cards">
        {anomaly ? (
          <InsightCard tone="warning" icon={<AlertTriangle />} label="Необычная трата" title={`${anomaly.title}: ${money(anomaly.amount)}`} text={`В ${anomaly.ratio.replace('.', ',')} раза выше обычной операции в категории «${anomaly.category_name}».`} action="Проверить операцию" onAction={() => navigate(`/transactions?search=${encodeURIComponent(anomaly.title)}`)} />
        ) : (
          <InsightCard tone="good" icon={<BadgeCheck />} label="Необычные траты" title="Всё спокойно" text="В этом месяце нет операций, заметно выше ваших обычных сумм." action="Все операции" onAction={() => navigate('/transactions')} />
        )}
        {overspend ? (
          <InsightCard tone="good" icon={<Sparkles />} label="Рекомендация" title={`Можно сэкономить ${money(Math.round(Number(overspend.amount)))}`} text={`Расходы на «${overspend.category_name}» идут выше вашего обычного темпа.`} action="Создать лимит" onAction={() => navigate('/categories')} />
        ) : (
          <InsightCard tone="good" icon={<Sparkles />} label="Рекомендация" title="Расходы в обычном темпе" text="Ни одна категория заметно не выбивается из среднего за прошлые месяцы." action="Открыть аналитику" onAction={() => navigate('/analytics')} />
        )}
        <InsightCard tone="info" icon={<Gauge />} label="Лимиты" title={limitTitle} text={limits.total ? `Лимиты заданы для категорий: ${limits.total}.` : 'Задайте лимиты, чтобы вовремя замечать перерасход.'} action="Проверить категории" onAction={() => navigate('/categories')} />
      </div>
      {plan.length > 0 && (
        <section className="card ai-plan">
          <div className="section-head">
            <div><h3>План оптимизации бюджета</h3><p>Самые крупные категории расходов</p></div>
            {Number(data.potential) > 0 && <span>Потенциал: +{money(Math.round(Number(data.potential)))}</span>}
          </div>
          <div className="plan-steps">
            {plan.map((item) => (
              <div className="plan-step" key={item.category_id}>
                <span className={item.has_limit ? 'done' : ''}>{item.has_limit && <Check />}</span>
                <div><b>{item.has_limit ? `Лимит на «${item.category_name}» задан` : `Установить лимит на «${item.category_name}»`}</b><small>В среднем {money(Math.round(Number(item.average)))} в месяц</small></div>
                <button aria-label="Открыть категории" onClick={() => navigate('/categories')}><ChevronRight /></button>
              </div>
            ))}
          </div>
        </section>
      )}
      <p className="ai-note">{forecast.method === 'ml' ? 'Прогноз строит модель, обученная на ваших операциях. Точность измерена на прошлых месяцах.' : user?.plan === 'premium' ? 'Для модели нужны полные операции хотя бы за три месяца, пока прогноз считается по темпу расходов.' : 'Подсказки считаются по статистике ваших операций. Обученные модели доступны в тарифе Premium.'}</p>
    </div>
  );
}
