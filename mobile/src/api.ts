import { File } from 'expo-file-system';

const API_URL = process.env.EXPO_PUBLIC_API_URL;
const HEALTH_TIMEOUT_MS = 5_000;
const SCAN_TIMEOUT_MS = 90_000;

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
  return request<Health>('/health', {}, HEALTH_TIMEOUT_MS);
}

export function getIngredients(): Promise<IngredientOption[]> {
  return request<IngredientOption[]>('/ingredients', {}, HEALTH_TIMEOUT_MS);
}

export function scanFridge(photos: ZonePhoto[]): Promise<ScanResult> {
  const body = new FormData();
  for (const photo of photos) {
    // fetch z Expo (SDK 58) nie przyjmuje starego { uri, name, type } z React Native,
    // tylko obiekt pliku, który umie oddać swoje bajty.
    body.append('photos', new File(photo.uri));
    body.append('zones', photo.zone);
  }
  return request<ScanResult>('/scan', { method: 'POST', body }, SCAN_TIMEOUT_MS);
}
