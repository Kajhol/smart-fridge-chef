import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { checkHealth, getIngredients, type IngredientOption, type UserProfile } from './src/api';
import type { FridgeItem } from './src/ItemsEditor';
import { loadProfile, saveProfile } from './src/profile';
import ProfileScreen from './src/ProfileScreen';
import { useRecipes } from './src/recipes';
import RecipesScreen from './src/RecipesScreen';
import ScanScreen from './src/ScanScreen';
import { colors, font, radius, spacing } from './src/theme';
import { AppButton } from './src/ui';

type Screen = 'recipes' | 'profile' | null;

function sortByName(list: IngredientOption[]): IngredientOption[] {
  return [...list].sort((a, b) => a.name_pl.localeCompare(b.name_pl, 'pl'));
}

// 1 produkt, 2 produkty, 5 produktów, 22 produkty, 12 produktów.
function productsText(count: number): string {
  if (count === 1) {
    return '1 produkt';
  }
  const last = count % 10;
  const lastTwo = count % 100;
  return last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14) ? `${count} produkty` : `${count} produktów`;
}

type BackendState = { kind: 'checking' } | { kind: 'ok'; model: string } | { kind: 'error'; message: string };

function BackendStatus() {
  const [state, setState] = useState<BackendState>({ kind: 'checking' });

  async function check() {
    setState({ kind: 'checking' });
    try {
      const health = await checkHealth();
      setState({ kind: 'ok', model: health.model });
    } catch (error) {
      setState({ kind: 'error', message: error instanceof Error ? error.message : String(error) });
    }
  }

  // Sprawdzamy od razu po starcie; dotknięcie plakietki sprawdza ponownie.
  useEffect(() => {
    check();
  }, []);

  const dotColor = state.kind === 'ok' ? colors.primary : state.kind === 'error' ? colors.danger : colors.muted;
  const text =
    state.kind === 'ok'
      ? `Backend OK · ${state.model}`
      : state.kind === 'error'
        ? 'Brak połączenia z backendem'
        : 'Łączę z backendem…';

  return (
    <Pressable onPress={check} style={styles.status}>
      <View style={styles.statusRow}>
        <View style={[styles.dot, { backgroundColor: dotColor }]} />
        <Text style={styles.statusText}>{text}</Text>
      </View>
      {state.kind === 'error' && (
        <Text style={styles.statusError}>{state.message} Dotknij, aby spróbować ponownie.</Text>
      )}
    </Pressable>
  );
}

function Main() {
  // Odstęp od notcha i paska systemowego: na każdym telefonie jest inny, więc bierzemy go z systemu.
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<UserProfile>(loadProfile);
  const [ingredients, setIngredients] = useState<IngredientOption[]>([]);
  const [dictionaryError, setDictionaryError] = useState<string | null>(null);
  const [items, setItems] = useState<FridgeItem[] | null>(null);
  const [screen, setScreen] = useState<Screen>(null);
  const recipes = useRecipes();
  const canSearch = items !== null && items.length > 0;

  // Słownik pobieramy raz, przy starcie. Bez niego działa skan, tylko nie da się dodać produktu,
  // przypisać pozycji spoza słownika ani wykluczyć składnika w profilu.
  useEffect(() => {
    getIngredients()
      .then((list) => setIngredients(sortByName(list)))
      .catch((caught) =>
        setDictionaryError(`Nie udało się pobrać słownika: ${caught instanceof Error ? caught.message : caught}`),
      );
  }, []);

  function onIngredientCreated(ingredient: IngredientOption) {
    setIngredients((previous) =>
      previous.some((item) => item.id === ingredient.id) ? previous : sortByName([...previous, ingredient]),
    );
  }

  function openRecipes() {
    if (items) {
      setScreen('recipes');
      recipes.ensure(items, profile);
    }
  }

  // Zapis na telefonie może się nie udać (brak miejsca), ale profil i tak działa do zamknięcia aplikacji.
  function updateProfile(next: UserProfile) {
    setProfile(next);
    saveProfile(next).catch((caught) => console.warn('Nie zapisano profilu', caught));
    if (screen === 'recipes' && items) {
      recipes.ensure(items, next);
    }
  }

  // Android w Expo działa edge-to-edge: okno nie kurczy się samo pod klawiaturą, więc bez tego
  // pola na dole listy (np. ilość) chowałyby się pod nią. "padding" działa na obu systemach.
  return (
    <KeyboardAvoidingView behavior="padding" style={styles.screen}>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.lg, paddingBottom: (canSearch ? 0 : insets.bottom) + spacing.xl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <View style={styles.titleRow}>
            <Text style={styles.title}>Smart Fridge Chef</Text>
            <Pressable onPress={() => setScreen('profile')} hitSlop={12} style={styles.profileButton}>
              <Text style={styles.profileButtonText}>⚙ Profil</Text>
            </Pressable>
          </View>
          <Text style={styles.subtitle}>Zrób zdjęcia lodówki, a my sprawdzimy, co w niej jest.</Text>
          <BackendStatus />
          {dictionaryError && <Text style={styles.statusError}>{dictionaryError}</Text>}
        </View>
        <ScanScreen
          items={items}
          onItemsChange={setItems}
          ingredients={ingredients}
          onIngredientCreated={onIngredientCreated}
        />
      </ScrollView>

      {/* Przycisk poza listą, więc widać go zawsze, bez przewijania na sam dół. */}
      {canSearch && (
        <View style={[styles.bar, { paddingBottom: insets.bottom + spacing.md }]}>
          <AppButton title={`Szukaj przepisów · ${productsText(items.length)}`} onPress={openRecipes} />
        </View>
      )}

      {screen === 'recipes' && items && (
        <RecipesScreen
          items={items}
          profile={profile}
          recipes={recipes}
          ingredients={ingredients}
          onSaveProfile={updateProfile}
          onClose={() => setScreen(null)}
        />
      )}
      {screen === 'profile' && (
        <ProfileScreen
          profile={profile}
          ingredients={ingredients}
          onSave={(next) => {
            updateProfile(next);
            setScreen(null);
          }}
          onClose={() => setScreen(null)}
        />
      )}
      <StatusBar style="dark" />
    </KeyboardAvoidingView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingHorizontal: spacing.lg,
    gap: spacing.lg,
  },
  header: {
    gap: spacing.sm,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  profileButton: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  profileButtonText: {
    fontSize: font.small,
    fontWeight: '600',
    color: colors.primary,
  },
  bar: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  title: {
    flexShrink: 1,
    fontSize: font.title,
    fontWeight: '700',
    color: colors.text,
  },
  subtitle: {
    fontSize: font.body,
    color: colors.muted,
  },
  status: {
    alignSelf: 'flex-start',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
  },
  statusText: {
    fontSize: font.small,
    color: colors.text,
  },
  statusError: {
    fontSize: font.small,
    color: colors.danger,
  },
});
