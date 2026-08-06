export const DEMO_CONFIG = {
  mode: 'concept' as 'concept' | 'approved',
  useFixtures: true,
  enableLiveRefresh: false,
  enableRequestCreation: false,
  enableExternalLinks: false,
  showBrandMark: false,
  showDemoWatermark: true,
} as const;

export const DEMO_DISABLED_MESSAGE =
  'Действие недоступно в демонстрационной среде.';

export const DEMO_DISCLAIMER =
  'Концепт пилотной интеграции для Aigenis Invest · Демонстрационная среда. Не является торговой системой и не содержит персональных данных клиентов.';

export const DEMO_PERSONA = {
  name: 'Марина К.',
  label: 'Частный инвестор',
  portfolio_byn: 50000,
  goal: 'Регулярный доход при умеренном риске',
};

export const SCORE_STATUS_LABEL: Record<string, string> = {
  attractive: 'Привлекательна',
  neutral: 'Нейтральна',
  review: 'Требует проверки',
  high_risk: 'Повышенный риск',
  no_data: 'Недостаточно данных',
};

export const SCORE_STATUS_DESC: Record<string, string> = {
  attractive: 'Стоит изучить в первую очередь',
  neutral: 'Требует сравнения с альтернативами',
  review: 'Есть значимые компромиссы',
  high_risk: 'Необходима дополнительная проверка',
  no_data: 'Автоматическое решение не принимается',
};

export const ALLOCATION_OPTIONS = [5, 10, 15] as const;

export const TERM_FILTER_LABEL: Record<string, string> = {
  all: 'Все сроки',
  up_to_1: 'До 1 года',
  '1_3': '1–3 года',
  '3_5': '3–5 лет',
  '5_plus': 'Более 5 лет',
};

export const MARKET_LABEL: Record<string, string> = {
  BCSE: 'BCSE',
  MOEX: 'MOEX',
};

export const CURRENCY_LABEL: Record<string, string> = {
  ALL: 'Все валюты',
  BYN: 'BYN',
  RUB: 'RUB',
  USD: 'USD',
  EUR: 'EUR',
};
