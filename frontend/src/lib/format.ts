const SYMBOLS: Record<string, string> = { RUB: '₽', USD: '$', EUR: '€' };

// Number здесь только для показа: все расчёты делает сервер в Decimal
export function money(value: string | number, currency = 'RUB'): string {
  const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(Number(value));
  return `${number} ${SYMBOLS[currency] ?? currency}`;
}

export function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function monthRange(offset = 0): { date_from: string; date_to: string } {
  const now = new Date();
  return {
    date_from: isoDate(new Date(now.getFullYear(), now.getMonth() + offset, 1)),
    date_to: isoDate(new Date(now.getFullYear(), now.getMonth() + offset + 1, 0)),
  };
}

export function monthTitle(offset = 0): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + offset, 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
}

export function initials(name: string): string {
  return name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase();
}

export const ROLE_LABEL = { owner: 'Владелец', admin: 'Администратор', member: 'Участник' } as const;

const DATIVE_MONTHS = ['январю', 'февралю', 'марту', 'апрелю', 'маю', 'июню', 'июлю', 'августу', 'сентябрю', 'октябрю', 'ноябрю', 'декабрю'];

export function monthDative(offset = 0): string {
  const now = new Date();
  return DATIVE_MONTHS[new Date(now.getFullYear(), now.getMonth() + offset, 1).getMonth()];
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Сравнивать неполный месяц с полным прошлым нечестно: в начале месяца всё «снизилось»
export function samePeriodRange(offset = -1): { date_from: string; date_to: string } {
  const now = new Date();
  const lastDay = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0).getDate();
  return {
    date_from: isoDate(new Date(now.getFullYear(), now.getMonth() + offset, 1)),
    date_to: isoDate(new Date(now.getFullYear(), now.getMonth() + offset, Math.min(now.getDate(), lastDay))),
  };
}

export function changePercent(current: number, previous: number): number | null {
  if (previous <= 0) return null;
  return Math.round(((current - previous) / previous) * 100);
}

export function signedPercent(value: number): string {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value)}%`;
}

export function signedMoney(value: number, currency = 'RUB'): string {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${money(Math.abs(value), currency)}`;
}

const EMOJI: [RegExp, string][] = [
  [/продукт/i, '🛒'], [/жиль|жкх|дом|ремонт/i, '🏠'], [/транспорт|такси/i, '🚕'], [/кафе|ресторан/i, '☕'],
  [/связь|интернет/i, '📱'], [/здоров/i, '💊'], [/развлеч/i, '🎬'], [/одежд/i, '👕'], [/красот/i, '💅'],
  [/подписк/i, '🔁'], [/техник/i, '💻'], [/путешеств/i, '✈️'], [/обучен/i, '📚'], [/зарплат/i, '💼'],
  [/кешб|процент/i, '💰'], [/подар/i, '🎁'],
];

export function categoryEmoji(name: string | undefined, type: 'income' | 'expense' | 'transfer'): string {
  if (type === 'transfer') return '🔄';
  return EMOJI.find(([pattern]) => pattern.test(name ?? ''))?.[1] ?? (type === 'income' ? '💵' : '🧾');
}

export const KIND_LABEL = { card: 'Банковская карта', savings: 'Накопительный счёт', deposit: 'Вклад', cash: 'Наличные' };

export const KIND_OPTIONS = Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label }));

export function plural(count: number, one: string, few: string, many: string): string {
  const tens = count % 100;
  const units = count % 10;
  if (tens >= 11 && tens <= 14) return `${count} ${many}`;
  if (units === 1) return `${count} ${one}`;
  if (units >= 2 && units <= 4) return `${count} ${few}`;
  return `${count} ${many}`;
}

export function dateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
}
