import { File, Paths } from 'expo-file-system';

import type { Allergen, Difficulty, UserProfile } from './api';

// Domyślny profil, taki sam jak UserProfile() w recipes/schema.py.
export const DEFAULT_PROFILE: UserProfile = {
  allergens: [],
  excluded_ingredients: [],
  max_difficulty: 'hard',
  max_time_min: null,
  servings: 2,
};

export const MIN_SERVINGS = 1;
export const MAX_SERVINGS = 12; // tak jak le=12 w schema.py

// Kolejność jak na liście alergenów w UE; nazwy takie, jakie zna użytkownik.
export const ALLERGENS: { value: Allergen; label: string }[] = [
  { value: 'gluten', label: 'gluten' },
  { value: 'milk', label: 'mleko' },
  { value: 'eggs', label: 'jajka' },
  { value: 'nuts', label: 'orzechy' },
  { value: 'peanuts', label: 'orzeszki ziemne' },
  { value: 'soy', label: 'soja' },
  { value: 'fish', label: 'ryby' },
  { value: 'crustaceans', label: 'skorupiaki' },
  { value: 'celery', label: 'seler' },
  { value: 'mustard', label: 'gorczyca' },
  { value: 'sesame', label: 'sezam' },
  { value: 'sulphites', label: 'siarczyny' },
];

export const DIFFICULTY_LABELS: Record<Difficulty, string> = { easy: 'łatwy', medium: 'średni', hard: 'trudny' };

// Profil leży w pliku w katalogu aplikacji: przetrwa zamknięcie aplikacji, a do tego nie trzeba nowej paczki.
const PROFILE_FILE = new File(Paths.document, 'profile.json');

// Odczyt synchroniczny, bo plik jest malutki, a profil jest potrzebny od pierwszego ekranu.
export function loadProfile(): UserProfile {
  try {
    if (!PROFILE_FILE.exists) {
      return DEFAULT_PROFILE;
    }
    // Brakujące pola (np. po dodaniu nowego w przyszłości) biorą wartość domyślną.
    return { ...DEFAULT_PROFILE, ...JSON.parse(PROFILE_FILE.textSync()) };
  } catch {
    return DEFAULT_PROFILE;
  }
}

export async function saveProfile(profile: UserProfile): Promise<void> {
  if (!PROFILE_FILE.exists) {
    PROFILE_FILE.create();
  }
  await PROFILE_FILE.write(JSON.stringify(profile));
}

function servingsText(servings: number): string {
  if (servings === 1) {
    return '1 porcja';
  }
  return servings <= 4 ? `${servings} porcje` : `${servings} porcji`;
}

// Jedna linijka do ekranu przepisów: „bez: jajka, mleko · do 30 min · 2 porcje”.
export function describeProfile(profile: UserProfile, namesById: Map<string, string>): string {
  const parts: string[] = [];
  if (profile.allergens.length > 0) {
    const labels = ALLERGENS.filter((a) => profile.allergens.includes(a.value)).map((a) => a.label);
    parts.push(`bez: ${labels.join(', ')}`);
  }
  if (profile.excluded_ingredients.length > 0) {
    const names = profile.excluded_ingredients.map((id) => namesById.get(id) ?? id);
    parts.push(`nie jem: ${names.join(', ')}`);
  }
  if (profile.max_difficulty === 'easy') {
    parts.push('tylko łatwe');
  } else if (profile.max_difficulty === 'medium') {
    parts.push('łatwe i średnie');
  }
  if (profile.max_time_min !== null) {
    parts.push(`do ${profile.max_time_min} min`);
  }
  parts.push(servingsText(profile.servings));
  return parts.join(' · ');
}
