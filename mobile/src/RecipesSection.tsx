import { useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { findRecipes, type Difficulty, type Recipe, type RecipeResponse, type UserProfile } from './api';
import type { FridgeItem } from './ItemsEditor';
import { colors, font, radius, spacing } from './theme';
import { AppButton, Badge, Card } from './ui';

const DIFFICULTY_LABELS: Record<Difficulty, string> = { easy: 'łatwy', medium: 'średni', hard: 'trudny' };

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
};

export default function RecipesSection({ items, profile }: Props) {
  // Wynik pamięta, dla jakiej listy i profilu powstał. Po każdej zmianie przestaje pasować, więc go nie pokazujemy.
  const [result, setResult] = useState<{ items: FridgeItem[]; profile: UserProfile; response: RecipeResponse } | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const response = result && result.items === items && result.profile === profile ? result.response : null;

  async function search() {
    setLoading(true);
    setError(null);
    try {
      // Backend chce kształtu FridgeItem z recipes/schema.py: bez key, confidence i visibility.
      const fridge = items.map(({ ingredient_id, label, quantity, unit }) => ({
        ingredient_id,
        label,
        quantity,
        unit,
      }));
      setResult({ items, profile, response: await findRecipes(fridge, profile) });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      <AppButton
        title={response ? 'Szukaj ponownie' : 'Szukaj przepisów'}
        onPress={search}
        loading={loading}
        disabled={items.length === 0}
      />
      {loading && <Text style={styles.hint}>To potrwa kilka sekund: AI wybiera przepisy i tłumaczy je na polski.</Text>}
      {error && (
        <Card style={styles.errorCard}>
          <Text style={styles.errorText}>{error}</Text>
        </Card>
      )}

      {response && (
        <>
          <View style={styles.header}>
            <Text style={styles.heading}>Przepisy</Text>
            <Text style={styles.hint}>{summary(response)}</Text>
          </View>
          {response.recipes.map((recipe, index) => (
            <RecipeCard key={recipe.id ?? index} recipe={recipe} />
          ))}
        </>
      )}
    </View>
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
  container: {
    gap: spacing.md,
  },
  header: {
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  heading: {
    fontSize: font.heading,
    fontWeight: '700',
    color: colors.text,
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
