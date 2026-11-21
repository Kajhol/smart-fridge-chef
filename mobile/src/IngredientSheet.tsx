import { useState } from 'react';
import { KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { addIngredient, type IngredientOption, type Unit } from './api';
import { colors, font, radius, spacing } from './theme';
import { AppButton, Badge } from './ui';

const MAX_RESULTS = 8;
const UNITS: { unit: Unit; label: string }[] = [
  { unit: 'pcs', label: 'sztuki' },
  { unit: 'g', label: 'gramy' },
  { unit: 'ml', label: 'mililitry' },
];

// "Jabłko" i "jablko" mają pasować do siebie: małe litery, bez ogonków.
function simplify(text: string): string {
  return text.toLowerCase().replace(/ł/g, 'l').normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
}

type Props = {
  title: string;
  initialQuery: string;
  defaultUnit: Unit;
  ingredients: IngredientOption[];
  // label: nazwa, która ma zostać na liście (zamiennik, np. "mandarynka" jako pomarańcza). Brak = nazwa ze słownika.
  onPick: (ingredient: IngredientOption, label?: string) => void;
  onCreated: (ingredient: IngredientOption) => void;
  onClose: () => void;
  // false: tylko wybór ze słownika, bez zamiennika i dodawania (np. wykluczenia w profilu).
  allowCreate?: boolean;
};

// Okno na cały ekran z polem wyszukiwania NA GÓRZE: klawiatura wysuwa się od dołu,
// więc nie może go zasłonić (tak było, gdy wyszukiwarka siedziała na dole listy).
export default function IngredientSheet({
  title,
  initialQuery,
  defaultUnit,
  ingredients,
  onPick,
  onCreated,
  onClose,
  allowCreate = true,
}: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [unit, setUnit] = useState<Unit>(defaultUnit);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Nazwa wpisana przed "Wybierz zamiennik". Gdy jest, szukamy zamiennika, a ta nazwa zostaje na liście (D-003).
  const [substituteFor, setSubstituteFor] = useState<string | null>(null);

  const needle = simplify(query);
  const matches = needle
    ? ingredients.filter((ingredient) => simplify(ingredient.name_pl).includes(needle)).slice(0, MAX_RESULTS)
    : [];
  const exactMatch = ingredients.some((ingredient) => simplify(ingredient.name_pl) === needle);
  const name = query.trim();

  function startSubstitute() {
    setSubstituteFor(name);
    setQuery('');
  }

  function cancelSubstitute() {
    setQuery(substituteFor ?? '');
    setSubstituteFor(null);
  }

  function choose(ingredient: IngredientOption) {
    onPick(ingredient, substituteFor ?? undefined);
  }

  async function create() {
    setCreating(true);
    setError(null);
    try {
      const ingredient = await addIngredient(name, unit);
      onCreated(ingredient);
      onPick(ingredient);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setCreating(false);
    }
  }

  return (
    <Modal visible animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      {/* Modal to osobne okno, więc potrzebuje własnego SafeAreaProvider, żeby znać swoje marginesy. */}
      <SafeAreaProvider>
        <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
          <KeyboardAvoidingView behavior="padding" style={styles.flex}>
            <View style={styles.header}>
              <Text style={styles.title} numberOfLines={1}>
                {substituteFor ? `Zamiennik dla „${substituteFor}”` : title}
              </Text>
              <Pressable onPress={substituteFor ? cancelSubstitute : onClose} hitSlop={12}>
                <Text style={styles.close}>{substituteFor ? 'Wróć' : 'Zamknij'}</Text>
              </Pressable>
            </View>
            {substituteFor && (
              <Text style={styles.small}>
                Na liście zostanie „{substituteFor}”, a przepisy potraktują produkt jak wybrany zamiennik.
              </Text>
            )}

            <TextInput
              style={styles.input}
              placeholder={substituteFor ? 'Szukaj zamiennika, np. pomarańcza' : 'Wpisz nazwę, np. mandarynka'}
              placeholderTextColor={colors.muted}
              value={query}
              onChangeText={setQuery}
              autoFocus
              selectTextOnFocus
              autoCorrect={false}
              returnKeyType="search"
            />

            <ScrollView contentContainerStyle={styles.results} keyboardShouldPersistTaps="handled">
              {matches.length > 0 && <Text style={styles.sectionTitle}>Ze słownika</Text>}
              {matches.map((ingredient) => (
                <Pressable
                  key={ingredient.id}
                  style={({ pressed }) => [styles.option, pressed && styles.optionPressed]}
                  onPress={() => choose(ingredient)}
                >
                  <Text style={styles.optionText}>{ingredient.name_pl}</Text>
                  {ingredient.custom && <Badge label="dodany" tone="info" />}
                </Pressable>
              ))}

              {!allowCreate && needle !== '' && matches.length === 0 && (
                <Text style={styles.small}>Nie ma tego w słowniku. Spróbuj innej nazwy.</Text>
              )}

              {allowCreate && needle !== '' && !exactMatch && !substituteFor && (
                <View style={styles.create}>
                  <Text style={styles.sectionTitle}>
                    {matches.length === 0 ? 'Nie ma tego w słowniku' : 'Nie ma dokładnie takiej pozycji'}
                  </Text>
                  <AppButton title="Wybierz zamiennik ze słownika" onPress={startSubstitute} />
                  <Text style={styles.small}>
                    Np. mandarynki jako pomarańcza: nazwa „{name}” zostanie, a przepisy będą działać od razu.
                  </Text>

                  <Text style={[styles.sectionTitle, styles.spaced]}>Nie ma zamiennika?</Text>
                  <Text style={styles.hint}>W czym liczysz „{name}”?</Text>
                  <View style={styles.units}>
                    {UNITS.map((option) => (
                      <Pressable
                        key={option.unit}
                        onPress={() => setUnit(option.unit)}
                        style={[styles.unit, unit === option.unit && styles.unitActive]}
                      >
                        <Text style={[styles.unitText, unit === option.unit && styles.unitTextActive]}>
                          {option.label}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                  <AppButton
                    title={`Dodaj „${name}” do słownika`}
                    variant="secondary"
                    onPress={create}
                    loading={creating}
                  />
                  <Text style={styles.small}>
                    Nowy produkt od razu pojawi się na liście, ale przepisy go nie znają, dopóki zespół nie dopisze mu
                    angielskich nazw.
                  </Text>
                  {error && <Text style={styles.error}>{error}</Text>}
                </View>
              )}
            </ScrollView>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </SafeAreaProvider>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  flex: {
    flex: 1,
    paddingHorizontal: spacing.lg,
    gap: spacing.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: spacing.lg,
  },
  title: {
    flex: 1,
    marginRight: spacing.md,
    fontSize: font.heading,
    fontWeight: '700',
    color: colors.text,
  },
  close: {
    fontSize: font.body,
    fontWeight: '600',
    color: colors.primary,
  },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    fontSize: font.body,
    color: colors.text,
  },
  results: {
    gap: spacing.sm,
    paddingBottom: spacing.xl,
  },
  sectionTitle: {
    fontSize: font.small,
    fontWeight: '600',
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  optionPressed: {
    backgroundColor: colors.primarySoft,
  },
  optionText: {
    fontSize: font.body,
    color: colors.text,
  },
  create: {
    gap: spacing.md,
    marginTop: spacing.sm,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
  },
  hint: {
    fontSize: font.body,
    color: colors.text,
  },
  units: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  unit: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  unitActive: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  unitText: {
    color: colors.muted,
  },
  unitTextActive: {
    color: colors.primary,
    fontWeight: '600',
  },
  spaced: {
    marginTop: spacing.md,
  },
  small: {
    fontSize: font.small,
    color: colors.muted,
  },
  error: {
    color: colors.danger,
  },
});
