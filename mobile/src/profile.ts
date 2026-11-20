import type { UserProfile } from './api';

// Domyślny profil, taki sam jak UserProfile() w recipes/schema.py. Ekran profilu będzie go zmieniał.
export const DEFAULT_PROFILE: UserProfile = {
  allergens: [],
  excluded_ingredients: [],
  max_difficulty: 'hard',
  max_time_min: null,
  servings: 2,
};
