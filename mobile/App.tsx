import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { checkHealth } from './src/api';
import ScanScreen from './src/ScanScreen';
import { colors, font, radius, spacing } from './src/theme';

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

  // Android w Expo działa edge-to-edge: okno nie kurczy się samo pod klawiaturą, więc bez tego
  // pola na dole listy (np. ilość) chowałyby się pod nią. "padding" działa na obu systemach.
  return (
    <KeyboardAvoidingView behavior="padding" style={styles.screen}>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.xl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <Text style={styles.title}>Smart Fridge Chef</Text>
          <Text style={styles.subtitle}>Zrób zdjęcia lodówki, a my sprawdzimy, co w niej jest.</Text>
          <BackendStatus />
        </View>
        <ScanScreen />
        <StatusBar style="dark" />
      </ScrollView>
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
  title: {
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
