export const THEME_KEY = 'walletly-theme';

export function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) ?? 'violet';
  } catch {
    // Браузер может запретить хранилище: тогда просто тема по умолчанию
    return 'violet';
  }
}
