import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Allergen, Difficulty, IngredientOption, UserProfile } from './api';
import IngredientSheet from './IngredientSheet';
import { ALLERGENS, MAX_SERVINGS, MIN_SERVINGS } from './profile';
import { colors, font, radius, spacing } from './theme';
import { AppButton, Card, Chip, ScreenModal } from './ui';

const TIME_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: 'bez limitu' },
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 45, label: '45 min' },
  { value: 60, label: '1 godz.' },
];

const DIFFICULTY_OPTIONS: { value: Difficulty; label: string }[] = [
  { value: 'easy', label: 'tylko łatwe' },
  { value: 'medium', label: 'łatwe i średnie' },
  { value: 'hard', label: 'wszystkie' },
];

type Props = {
  profile: UserProfile;
  ingredients: IngredientOption[];
  onSave: (profile: UserProfile) => void;
  onClose: () => void;
};

// Zmiany są w wersji roboczej i trafiają do aplikacji dopiero po „Zapisz”. „Anuluj” niczego nie zmienia.
export default function ProfileScreen({ profile, ingredients, onSave, onClose }: Props) {
  const [draft, setDraft] = useState(profile);
  const [picking, setPicking] = useState(false);

  // Produkty dodane z aplikacji (custom_…) nie występują w żadnym przepisie, więc wykluczanie ich nic nie da.
  const dictionary = useMemo(() => ingredients.filter((ingredient) => !ingredient.custom), [ingredients]);
  const namesById = useMemo(
    () => new Map(ingredients.map((ingredient) => [ingredient.id, ingredient.name_pl])),
    [ingredients],
  );

  function toggleAllergen(allergen: Allergen) {
    const allergens = draft.allergens.includes(allergen)
      ? draft.allergens.filter((a) => a !== allergen)
      : [...draft.allergens, allergen];
    setDraft({ ...draft, allergens });
  }

  function exclude(ingredient: IngredientOption) {
    if (!draft.excluded_ingredients.includes(ingredient.id)) {
      setDraft({ ...draft, excluded_ingredients: [...draft.excluded_ingredients, ingredient.id] });
    }
    setPicking(false);
  }

  function unexclude(id: string) {
    setDraft({ ...draft, excluded_ingredients: draft.excluded_ingredients.filter((item) => item !== id) });
  }

  function changeServings(delta: number) {
    const servings = Math.min(MAX_SERVINGS, Math.max(MIN_SERVINGS, draft.servings + delta));
    setDraft({ ...draft, servings });
  }

  return (
    <ScreenModal
      title="Twój profil"
      closeLabel="Anuluj"
      onClose={onClose}
      footer={<AppButton title="Zapisz profil" onPress={() => onSave(draft)} />}
    >
      <Card>
        <View style={styles.sectionText}>
          <Text style={styles.heading}>Alergie</Text>
          <Text style={styles.hint}>Przepisy z tymi alergenami w ogóle się nie pokażą.</Text>
        </View>
        <View style={styles.chips}>
          {ALLERGENS.map((allergen) => (
            <Chip
              key={allergen.value}
              label={allergen.label}
              selected={draft.allergens.includes(allergen.value)}
              onPress={() => toggleAllergen(allergen.value)}
            />
          ))}
        </View>
      </Card>

      <Card>
        <View style={styles.sectionText}>
          <Text style={styles.heading}>Nie jem</Text>
          <Text style={styles.hint}>Składniki, których nie jesz albo nie lubisz, np. mięso.</Text>
        </View>
        {draft.excluded_ingredients.length > 0 && (
          <View style={styles.chips}>
            {draft.excluded_ingredients.map((id) => (
              <Chip key={id} label={`${namesById.get(id) ?? id}  ✕`} selected onPress={() => unexclude(id)} />
            ))}
          </View>
        )}
        <AppButton title="+ Dodaj składnik" variant="secondary" onPress={() => setPicking(true)} />
      </Card>

      <Card>
        <Text style={styles.heading}>Czas przygotowania</Text>
        <View style={styles.chips}>
          {TIME_OPTIONS.map((option) => (
            <Chip
              key={option.label}
              label={option.label}
              selected={draft.max_time_min === option.value}
              onPress={() => setDraft({ ...draft, max_time_min: option.value })}
            />
          ))}
        </View>
      </Card>

      <Card>
        <Text style={styles.heading}>Trudność</Text>
        <View style={styles.chips}>
          {DIFFICULTY_OPTIONS.map((option) => (
            <Chip
              key={option.value}
              label={option.label}
              selected={draft.max_difficulty === option.value}
              onPress={() => setDraft({ ...draft, max_difficulty: option.value })}
            />
          ))}
        </View>
      </Card>

      <Card>
        <View style={styles.sectionText}>
          <Text style={styles.heading}>Porcje</Text>
          <Text style={styles.hint}>
            Dla ilu osób gotujesz. Przepis od AI dostaje tę liczbę, a przepisy z bazy pokazują ilości z oryginału.
          </Text>
        </View>
        <View style={styles.stepper}>
          <Pressable
            onPress={() => changeServings(-1)}
            disabled={draft.servings <= MIN_SERVINGS}
            style={[styles.stepperButton, draft.servings <= MIN_SERVINGS && styles.disabled]}
            hitSlop={8}
          >
            <Text style={styles.stepperSign}>−</Text>
          </Pressable>
          <Text style={styles.stepperValue}>{draft.servings}</Text>
          <Pressable
            onPress={() => changeServings(1)}
            disabled={draft.servings >= MAX_SERVINGS}
            style={[styles.stepperButton, draft.servings >= MAX_SERVINGS && styles.disabled]}
            hitSlop={8}
          >
            <Text style={styles.stepperSign}>+</Text>
          </Pressable>
        </View>
      </Card>

      {picking && (
        <IngredientSheet
          title="Czego nie jesz?"
          initialQuery=""
          defaultUnit="pcs"
          ingredients={dictionary}
          onPick={exclude}
          onCreated={() => {}}
          onClose={() => setPicking(false)}
          allowCreate={false}
        />
      )}
    </ScreenModal>
  );
}

const styles = StyleSheet.create({
  sectionText: {
    gap: spacing.xs,
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
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
  },
  stepperButton: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primarySoft,
  },
  stepperSign: {
    fontSize: 24,
    fontWeight: '600',
    color: colors.primary,
  },
  stepperValue: {
    minWidth: 32,
    textAlign: 'center',
    fontSize: font.title,
    fontWeight: '700',
    color: colors.text,
  },
  disabled: {
    opacity: 0.4,
  },
});
