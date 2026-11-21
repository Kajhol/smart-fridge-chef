import { useMemo, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import type { IngredientOption, Recipe, RecipeResponse, UserProfile } from './api';
import type { FridgeItem } from './ItemsEditor';
import { DIFFICULTY_LABELS, describeProfile } from './profile';
import ProfileScreen from './ProfileScreen';
import { matches, type Recipes } from './recipes';
import { colors, font, radius, spacing } from './theme';
import { AppButton, Badge, Card, ScreenModal } from './ui';

// Tytuły z Food.com są małymi literami ("cheddar omelette").
function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Przepis od AI przychodzi tylko wtedy, gdy z bazy nic nie pasuje (D-013), więc "1 z 0 pasujących" nie ma sensu.
function summary(response: RecipeResponse): string {
  const count = response.recipes.length;
  if (count === 0) {
    return 'Nie znalazłem przepisu, w którym brakuje najwyżej 2 składników. Dodaj produkty albo złagodź profil.';
  }
  if (response.candidates_considered === 0) {
    return 'Żaden przepis z bazy nie pasuje do Twoich produktów, więc AI ułożyło własny. Sprawdź go przed gotowaniem.';
  }
  return `Najlepsze ${count} z ${response.candidates_considered} pasujących przepisów.`;
}

type Props = {
  items: FridgeItem[];
  profile: UserProfile;
  recipes: Recipes;
  ingredients: IngredientOption[];
  onSaveProfile: (profile: UserProfile) => void;
  onClose: () => void;
};

// Wyszukiwanie startuje przy otwarciu ekranu (App.tsx), a wyniki trzyma useRecipes, więc po „Wróć”
// i ponownym otwarciu bez zmian na liście nie pytamy backendu drugi raz.
export default function RecipesScreen({ items, profile, recipes, ingredients, onSaveProfile, onClose }: Props) {
  const [editingProfile, setEditingProfile] = useState(false);
  const namesById = useMemo(
    () => new Map(ingredients.map((ingredient) => [ingredient.id, ingredient.name_pl])),
    [ingredients],
  );
  const response = matches(recipes.result, items, profile) ? recipes.result.response : null;

  function saveProfile(next: UserProfile) {
    setEditingProfile(false);
    onSaveProfile(next);
  }

  return (
    <ScreenModal title="Przepisy" onClose={onClose}>
      <Card style={styles.profileCard}>
        <Text style={styles.small}>Dla {items.length} produktów z lodówki i Twojego profilu:</Text>
        <Text style={styles.profileText}>{describeProfile(profile, namesById)}</Text>
        <AppButton title="Zmień profil" variant="secondary" onPress={() => setEditingProfile(true)} />
      </Card>

      {recipes.loading && (
        <Card style={styles.loadingCard}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.hint}>AI wybiera przepisy i tłumaczy je na polski. To potrwa kilka sekund.</Text>
        </Card>
      )}

      {recipes.error && !recipes.loading && (
        <Card style={styles.errorCard}>
          <Text style={styles.errorText}>{recipes.error}</Text>
          <AppButton title="Spróbuj ponownie" onPress={() => recipes.search(items, profile)} />
        </Card>
      )}

      {response && !recipes.loading && (
        <>
          <Text style={styles.hint}>{summary(response)}</Text>
          {response.recipes.map((recipe, index) => (
            <RecipeCard key={recipe.id ?? index} recipe={recipe} />
          ))}
          <AppButton title="Szukaj jeszcze raz" variant="ghost" onPress={() => recipes.search(items, profile)} />
        </>
      )}

      {editingProfile && (
        <ProfileScreen
          profile={profile}
          ingredients={ingredients}
          onSave={saveProfile}
          onClose={() => setEditingProfile(false)}
        />
      )}
    </ScreenModal>
  );
}

function RecipeCard({ recipe }: { recipe: Recipe }) {
  const [open, setOpen] = useState(false);
  const missing = recipe.ingredients.filter((ingredient) => ingredient.status === 'missing');
  const fromAi = recipe.source === 'ai_generated';
  const meta = [
    recipe.time_min !== null ? `${recipe.time_min} min` : null,
    DIFFICULTY_LABELS[recipe.difficulty],
    recipe.kcal_per_serving !== null ? `${Math.round(recipe.kcal_per_serving)} kcal/porcja` : null,
    recipe.servings !== null ? `porcje: ${recipe.servings}` : null,
  ].filter(Boolean);

  return (
    <Card>
      <Pressable onPress={() => setOpen(!open)} style={styles.cardTop}>
        {fromAi && <Badge label="wygenerowany przez AI" tone="info" />}
        <Text style={styles.title}>{capitalize(recipe.title)}</Text>
        <Text style={styles.meta}>{meta.join(' · ')}</Text>
        <Text style={styles.description}>{recipe.description}</Text>
      </Pressable>

      <View style={styles.chips}>
        {recipe.ingredients.map((ingredient) => (
          <Badge
            key={ingredient.ingredient_id}
            label={ingredient.name_pl}
            tone={
              ingredient.status === 'in_fridge' ? 'success' : ingredient.status === 'missing' ? 'danger' : 'neutral'
            }
          />
        ))}
      </View>

      {missing.length > 0 && (
        <View style={styles.shopping}>
          <Text style={styles.shoppingTitle}>Do kupienia</Text>
          <Text style={styles.shoppingText}>{missing.map((ingredient) => ingredient.name_pl).join(', ')}</Text>
        </View>
      )}

      {open && (
        <View style={styles.details}>
          <Text style={styles.sectionTitle}>Składniki</Text>
          {recipe.ingredient_lines.map((line, index) => (
            <Text key={index} style={styles.line}>
              • {line}
            </Text>
          ))}

          {recipe.substitutions.length > 0 && (
            <>
              <Text style={styles.sectionTitle}>Zamienniki</Text>
              {recipe.substitutions.map((substitution) => (
                <Text key={substitution.missing_id} style={styles.line}>
                  • {substitution.suggestion}
                </Text>
              ))}
            </>
          )}

          <Text style={styles.sectionTitle}>Przygotowanie</Text>
          {recipe.steps.map((step, index) => (
            <View key={index} style={styles.step}>
              <Text style={styles.stepNumber}>{index + 1}</Text>
              <Text style={styles.stepText}>{capitalize(step)}</Text>
            </View>
          ))}

          {!fromAi && recipe.url && (
            <AppButton title="Otwórz na food.com" variant="ghost" onPress={() => Linking.openURL(recipe.url!)} />
          )}
        </View>
      )}

      <AppButton title={open ? 'Zwiń' : 'Pokaż przepis'} variant="secondary" onPress={() => setOpen(!open)} />
    </Card>
  );
}

const styles = StyleSheet.create({
  profileCard: {
    gap: spacing.sm,
  },
  small: {
    fontSize: font.small,
    color: colors.muted,
  },
  profileText: {
    fontSize: font.body,
    fontWeight: '600',
    color: colors.text,
  },
  loadingCard: {
    alignItems: 'center',
  },
  hint: {
    fontSize: font.body,
    color: colors.muted,
  },
  errorCard: {
    backgroundColor: colors.dangerSoft,
    borderColor: colors.dangerSoft,
  },
  errorText: {
    color: colors.danger,
    fontSize: font.body,
  },
  cardTop: {
    gap: spacing.xs,
  },
  title: {
    fontSize: font.heading,
    fontWeight: '700',
    color: colors.text,
  },
  meta: {
    fontSize: font.small,
    color: colors.muted,
  },
  description: {
    fontSize: font.body,
    color: colors.text,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  shopping: {
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.dangerSoft,
    gap: 2,
  },
  shoppingTitle: {
    fontSize: font.small,
    fontWeight: '700',
    color: colors.danger,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  shoppingText: {
    fontSize: font.body,
    color: colors.text,
  },
  details: {
    gap: spacing.sm,
  },
  sectionTitle: {
    fontSize: font.small,
    fontWeight: '700',
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.sm,
  },
  line: {
    fontSize: font.body,
    color: colors.text,
  },
  step: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  stepNumber: {
    width: 24,
    height: 24,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    color: colors.primary,
    fontWeight: '700',
    textAlign: 'center',
    lineHeight: 24,
  },
  stepText: {
    flex: 1,
    fontSize: font.body,
    color: colors.text,
  },
});
