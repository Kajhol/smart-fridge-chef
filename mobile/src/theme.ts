// Wspólne kolory, odstępy i rozmiary. Komponenty biorą wartości stąd, a nie wpisują ich na sztywno.
export const colors = {
  background: '#F3F6F2',
  surface: '#FFFFFF',
  primary: '#2F7D4F',
  primaryPressed: '#256640',
  primarySoft: '#E3F1E8',
  text: '#1C2421',
  muted: '#6B7570',
  border: '#E2E7E3',
  danger: '#C53B2F',
  dangerSoft: '#FBE9E7',
  warning: '#B45F06',
  warningSoft: '#FDF0DC',
  info: '#2563EB',
  infoSoft: '#E5EDFD',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

export const font = {
  title: 26,
  heading: 18,
  body: 16,
  small: 13,
} as const;
