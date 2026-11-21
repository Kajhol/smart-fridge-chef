import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { colors, font, radius, spacing } from './theme';

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

type AppButtonProps = {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
};

// Własny przycisk zamiast Button z React Native, który na Androidzie jest niebieski
// i PISANY WIELKIMI LITERAMI, a na iPhonie wygląda jak goły link.
export function AppButton({ title, onPress, variant = 'primary', disabled, loading, style }: AppButtonProps) {
  const inactive = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      style={({ pressed }) => [
        styles.button,
        buttonStyles[variant],
        pressed && variant === 'primary' && { backgroundColor: colors.primaryPressed },
        pressed && variant !== 'primary' && styles.pressed,
        inactive && styles.inactive,
        style,
      ]}
    >
      {loading && <ActivityIndicator color={variant === 'primary' ? colors.surface : colors.primary} />}
      <Text style={[styles.buttonText, buttonTextStyles[variant]]}>{title}</Text>
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

type BadgeTone = 'neutral' | 'warning' | 'info' | 'success' | 'danger';

const badgeColors: Record<BadgeTone, { background: string; text: string }> = {
  neutral: { background: colors.background, text: colors.muted },
  warning: { background: colors.warningSoft, text: colors.warning },
  info: { background: colors.infoSoft, text: colors.info },
  success: { background: colors.primarySoft, text: colors.primary },
  danger: { background: colors.dangerSoft, text: colors.danger },
};

export function Badge({ label, tone = 'neutral' }: { label: string; tone?: BadgeTone }) {
  const palette = badgeColors[tone];
  return (
    <View style={[styles.badge, { backgroundColor: palette.background }]}>
      <Text style={[styles.badgeText, { color: palette.text }]}>{label}</Text>
    </View>
  );
}

// Pasek "1 — 2 — 3" nad zdjęciami: zrobione kroki na zielono, bieżący obwiedziony.
export function StepProgress({ labels, current }: { labels: string[]; current: number }) {
  return (
    <View style={styles.steps}>
      {labels.map((label, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <View key={label} style={styles.step}>
            <View style={[styles.stepDot, done && styles.stepDotDone, active && styles.stepDotActive]}>
              <Text style={[styles.stepNumber, active && styles.stepNumberStrong, done && styles.stepNumberDone]}>
                {done ? '✓' : index + 1}
              </Text>
            </View>
            <Text style={[styles.stepLabel, active && styles.stepLabelActive]} numberOfLines={1}>
              {label}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

// Pigułka do wyboru (alergen, czas, trudność). Zaznaczona jest zielona.
export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.chip, selected && styles.chipSelected, pressed && styles.pressed]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

type ScreenModalProps = {
  title: string;
  onClose: () => void;
  closeLabel?: string;
  children: ReactNode;
  footer?: ReactNode; // przycisk przyklejony do dołu, np. „Zapisz”
};

// Osobny ekran na cały telefon (przepisy, profil). Zamiast nawigacji: Modal, tak jak okno wyszukiwania
// produktów. Androidowy przycisk „wstecz” woła onRequestClose, więc działa jak „Wróć”.
export function ScreenModal({ title, onClose, closeLabel = 'Wróć', children, footer }: ScreenModalProps) {
  return (
    <Modal visible animationType="slide" presentationStyle="fullScreen" onRequestClose={onClose}>
      {/* Modal to osobne okno, więc potrzebuje własnego SafeAreaProvider, żeby znać swoje marginesy. */}
      <SafeAreaProvider>
        <SafeAreaView style={styles.modalScreen} edges={['top', 'bottom']}>
          <View style={styles.modalHeader}>
            <Pressable onPress={onClose} hitSlop={12} style={styles.modalBack}>
              <Text style={styles.modalBackText}>← {closeLabel}</Text>
            </Pressable>
            <Text style={styles.modalTitle}>{title}</Text>
          </View>
          <ScrollView contentContainerStyle={styles.modalContent} keyboardShouldPersistTaps="handled">
            {children}
          </ScrollView>
          {footer && <View style={styles.modalFooter}>{footer}</View>}
        </SafeAreaView>
      </SafeAreaProvider>
    </Modal>
  );
}

const buttonStyles = StyleSheet.create({
  primary: { backgroundColor: colors.primary },
  secondary: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.primary },
  danger: { backgroundColor: colors.dangerSoft },
  ghost: { backgroundColor: 'transparent' },
});

const buttonTextStyles = StyleSheet.create({
  primary: { color: colors.surface },
  secondary: { color: colors.primary },
  danger: { color: colors.danger },
  ghost: { color: colors.muted },
});

const styles = StyleSheet.create({
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    minHeight: 48,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
  },
  buttonText: {
    fontSize: font.body,
    fontWeight: '600',
  },
  pressed: {
    opacity: 0.7,
  },
  inactive: {
    opacity: 0.5,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  badgeText: {
    fontSize: font.small,
    fontWeight: '600',
  },
  steps: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  step: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.xs,
  },
  stepDot: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.background,
    borderWidth: 2,
    borderColor: colors.border,
  },
  stepDotDone: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  stepDotActive: {
    borderColor: colors.primary,
  },
  stepNumber: {
    color: colors.muted,
    fontWeight: '600',
  },
  stepNumberStrong: {
    color: colors.text,
  },
  stepNumberDone: {
    color: colors.surface,
  },
  stepLabel: {
    fontSize: font.small,
    color: colors.muted,
  },
  stepLabelActive: {
    color: colors.text,
    fontWeight: '600',
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipSelected: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  chipText: {
    fontSize: font.body,
    color: colors.muted,
  },
  chipTextSelected: {
    color: colors.primary,
    fontWeight: '600',
  },
  modalScreen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  modalHeader: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  modalBack: {
    alignSelf: 'flex-start',
  },
  modalBackText: {
    fontSize: font.body,
    fontWeight: '600',
    color: colors.primary,
  },
  modalTitle: {
    fontSize: font.title,
    fontWeight: '700',
    color: colors.text,
  },
  modalContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.lg,
  },
  modalFooter: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
