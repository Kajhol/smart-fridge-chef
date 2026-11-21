import { File } from 'expo-file-system';

const API_URL = process.env.EXPO_PUBLIC_API_URL;
const SHORT_TIMEOUT_MS = 5_000;
const SCAN_TIMEOUT_MS = 90_000;
const SAVE_TIMEOUT_MS = 30_000;
// Z LLM (D-013) jedno zapytanie to 4 wywołania modelu, a Gemini przy przeciążeniu sam ponawia próby.
const RECIPES_TIMEOUT_MS = 60_000;

export type Health = {
  status: string;
  model: string;
};

export type Zone = 'door' | 'shelves_upper' | 'shelves_lower' | 'extra';
export type Unit = 'pcs' | 'g' | 'ml';
export type Confidence = 'low' | 'medium' | 'high';

export type DetectedItem = {
  ingredient_id: string | null;
  label: string;
  quantity: number;
  unit: Unit;
  confidence: Confidence;
};

export type ScanResult = {
  items: DetectedItem[];
};

export type IngredientOption = {
  id: string;
  name_pl: string;
  unit: Unit;
  custom: boolean;
};

// Ewaluacja (D-003): czy produkt widać na zdjęciach. hidden = jest w lodówce, ale na zdjęciach go nie ma.
export type Visibility = 'visible' | 'partial' | 'hidden';

export type TruthItem = {
  ingredient_id: string | null;
  label: string;
  quantity: number;
  unit: Unit;
  visibility: Visibility;
};

// Część ScanMetrics z evaluation.py, której używa aplikacja.
export type ScanMetrics = {
  expected: number;
  predicted: number;
  found: number;
  recall: number | null;
  recall_seen: number | null;
  precision: number | null;
  f1: number | null;
  missed: string[];
  hallucinations: string[];
  duplicates: string[];
  unknown_expected: number;
};

export type SavedScan = {
  scan_id: string;
  metrics: ScanMetrics;
};

// --- Przepisy: kontrakt z src/smart_fridge_chef/recipes/schema.py (D-009, D-010, D-012) ---

export type Allergen =
  | 'celery'
  | 'crustaceans'
  | 'eggs'
  | 'fish'
  | 'gluten'
  | 'milk'
  | 'mustard'
  | 'nuts'
  | 'peanuts'
  | 'sesame'
  | 'soy'
  | 'sulphites';
export type Difficulty = 'easy' | 'medium' | 'hard';
export type IngredientStatus = 'in_fridge' | 'missing' | 'pantry';

export type RecipeFridgeItem = {
  ingredient_id: string | null;
  label: string;
  quantity: number;
  unit: Unit;
};

export type UserProfile = {
  allergens: Allergen[];
  excluded_ingredients: string[];
  max_difficulty: Difficulty;
  max_time_min: number | null;
  servings: number;
};

export type RecipeIngredient = {
  ingredient_id: string;
  name_pl: string;
  status: IngredientStatus;
};

export type Recipe = {
  id: string | null;
  source: 'database' | 'ai_generated';
  title: string;
  description: string;
  servings: number | null;
  time_min: number | null;
  difficulty: Difficulty;
  kcal_per_serving: number | null;
  ingredients: RecipeIngredient[];
  ingredient_lines: string[];
  substitutions: { missing_id: string; suggestion: string }[];
  steps: string[];
  url: string | null;
};

export type RecipeResponse = {
  recipes: Recipe[];
  candidates_considered: number;
};

export type ZonePhoto = {
  zone: Zone;
  uri: string;
};

async function request<T>(path: string, init: RequestInit, timeoutMs: number): Promise<T> {
  if (!API_URL) {
    throw new Error('Brak EXPO_PUBLIC_API_URL w mobile/.env.local');
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
    return await response.json();
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Brak odpowiedzi z ${API_URL} po ${timeoutMs / 1000} s.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') {
      return body.detail;
    }
  } catch {
    // odpowiedź nie była JSON-em, zostaje sam kod
  }
  return `Backend odpowiedział kodem ${response.status}`;
}

export function checkHealth(): Promise<Health> {
  return request<Health>('/health', {}, SHORT_TIMEOUT_MS);
}

export function getIngredients(): Promise<IngredientOption[]> {
  return request<IngredientOption[]>('/ingredients', {}, SHORT_TIMEOUT_MS);
}

export function addIngredient(name_pl: string, unit: Unit): Promise<IngredientOption> {
  return request<IngredientOption>(
    '/ingredients',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name_pl, unit }),
    },
    SHORT_TIMEOUT_MS,
  );
}

function photosForm(photos: ZonePhoto[]): FormData {
  const body = new FormData();
  for (const photo of photos) {
    // fetch z Expo (SDK 58) nie przyjmuje starego { uri, name, type } z React Native,
    // tylko obiekt pliku, który umie oddać swoje bajty.
    body.append('photos', new File(photo.uri));
    body.append('zones', photo.zone);
  }
  return body;
}

export function scanFridge(photos: ZonePhoto[]): Promise<ScanResult> {
  return request<ScanResult>('/scan', { method: 'POST', body: photosForm(photos) }, SCAN_TIMEOUT_MS);
}

// Zapis do zbioru testowego: te same zdjęcia, odpowiedź modelu bez poprawek i lista po korekcie (wzorzec).
export function saveScan(
  photos: ZonePhoto[],
  prediction: ScanResult,
  items: TruthItem[],
  seconds: number | null,
): Promise<SavedScan> {
  const body = photosForm(photos);
  body.append('prediction', JSON.stringify(prediction));
  body.append('truth_items', JSON.stringify(items));
  if (seconds !== null) {
    body.append('seconds', String(seconds));
  }
  return request<SavedScan>('/scans', { method: 'POST', body }, SAVE_TIMEOUT_MS);
}

export function findRecipes(items: RecipeFridgeItem[], profile: UserProfile): Promise<RecipeResponse> {
  return request<RecipeResponse>(
    '/recipes',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items, profile }),
    },
    RECIPES_TIMEOUT_MS,
  );
}
