import { useRef, useState } from 'react';

import { findRecipes, type RecipeResponse, type UserProfile } from './api';
import type { FridgeItem } from './ItemsEditor';

// Wynik pamięta, dla jakiej listy i profilu powstał. Gdy któreś się zmieni, wynik przestaje pasować.
export type RecipeResult = { items: FridgeItem[]; profile: UserProfile; response: RecipeResponse };

export function matches(
  result: RecipeResult | null,
  items: FridgeItem[],
  profile: UserProfile,
): result is RecipeResult {
  return result !== null && result.items === items && result.profile === profile;
}

// Stan wyszukiwania trzymamy nad ekranem przepisów: po zamknięciu i ponownym otwarciu ekranu
// wyniki zostają, więc nie wołamy LLM drugi raz (limit Gemini: 15 zapytań na minutę, D-013 to 4 na wyszukiwanie).
export function useRecipes() {
  const [result, setResult] = useState<RecipeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Gdy w trakcie wyszukiwania zmieni się profil, liczy się tylko ostatnie zapytanie.
  const latest = useRef(0);

  async function search(items: FridgeItem[], profile: UserProfile) {
    latest.current += 1;
    const id = latest.current;
    setLoading(true);
    setError(null);
    try {
      // Backend chce kształtu FridgeItem z recipes/schema.py: bez key, confidence i visibility.
      const fridge = items.map(({ ingredient_id, label, quantity, unit }) => ({ ingredient_id, label, quantity, unit }));
      const response = await findRecipes(fridge, profile);
      if (id === latest.current) {
        setResult({ items, profile, response });
      }
    } catch (caught) {
      if (id === latest.current) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      if (id === latest.current) {
        setLoading(false);
      }
    }
  }

  // Szuka tylko wtedy, gdy nie ma wyniku dla tej listy i tego profilu.
  function ensure(items: FridgeItem[], profile: UserProfile) {
    if (!matches(result, items, profile)) {
      void search(items, profile);
    }
  }

  return { result, loading, error, search, ensure };
}

export type Recipes = ReturnType<typeof useRecipes>;
