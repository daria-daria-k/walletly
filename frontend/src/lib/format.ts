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
