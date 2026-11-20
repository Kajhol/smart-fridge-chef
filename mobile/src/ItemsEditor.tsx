import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { Confidence, DetectedItem, IngredientOption, Unit, Visibility } from './api';
import IngredientSheet from './IngredientSheet';
import { colors, font, radius, spacing } from './theme';
import { AppButton, Badge, Card } from './ui';

// Pozycja na ekranie korekty. Kształt jak DetectedItem; confidence nie ma, gdy dodano ją ręcznie (D-009).
export type FridgeItem = {
  key: string;
  ingredient_id: string | null;
  label: string;
  quantity: number;
  unit: Unit;
  confidence?: Confidence;
  visibility?: Visibility; // tylko przy zapisie do ewaluacji; brak = visible
};

const VISIBILITY_OPTIONS: { value: Visibility; label: string }[] = [
  { value: 'visible', label: 'widać' },
  { value: 'partial', label: 'częściowo' },
  { value: 'hidden', label: 'schowane' },
];

const UNIT_LABELS: Record<Unit, string> = { pcs: 'szt.', g: 'g', ml: 'ml' };

let nextKey = 0;
function newKey(): string {
  nextKey += 1;
  return String(nextKey);
}

export function toFridgeItems(items: DetectedItem[]): FridgeItem[] {
  return items.map((item) => ({ ...item, key: newKey() }));
}

type QuantityInputProps = {
  value: number;
  onChange: (value: number) => void;
};

// Tekst trzymamy osobno, bo w trakcie pisania "0," albo "" nie jest jeszcze liczbą.
// Liczbę zapisujemy dopiero po wyjściu z pola; zła wartość wraca do poprzedniej.
function QuantityInput({ value, onChange }: QuantityInputProps) {
  const [text, setText] = useState(String(value));

  function commit() {
    const parsed = Number(text.replace(',', '.'));
    if (Number.isFinite(parsed) && parsed > 0) {
      onChange(parsed);
      setText(String(parsed));
    } else {
      setText(String(value));
    }
  }

  return (
    <TextInput
      style={styles.quantity}
      value={text}
      onChangeText={setText}
      onEndEditing={commit}
      keyboardType="decimal-pad"
      selectTextOnFocus
    />
  );
}

type Props = {
  items: FridgeItem[];
  ingredients: IngredientOption[];
  onChange: (items: FridgeItem[]) => void;
  onIngredientCreated: (ingredient: IngredientOption) => void;
  showVisibility?: boolean;
};

// Co jest otwarte w oknie wyszukiwania: dodawanie nowej pozycji albo zmiana istniejącej.
type Sheet = { mode: 'new' } | { mode: 'edit'; key: string };

export default function ItemsEditor({ items, ingredients, onChange, onIngredientCreated, showVisibility }: Props) {
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const editedItem = sheet?.mode === 'edit' ? items.find((item) => item.key === sheet.key) : undefined;

  const byId = useMemo(() => new Map(ingredients.map((ingredient) => [ingredient.id, ingredient])), [ingredients]);
  const unknownCount = items.filter((item) => item.ingredient_id === null).length;

  function update(key: string, changes: Partial<FridgeItem>) {
    onChange(items.map((item) => (item.key === key ? { ...item, ...changes } : item)));
  }

  function remove(key: string) {
    onChange(items.filter((item) => item.key !== key));
  }

  // Wybór ze słownika zmienia też nazwę: "owoce w folii" staje się "mandarynka".
  function pick(ingredient: IngredientOption) {
    const changes = { ingredient_id: ingredient.id, label: ingredient.name_pl, unit: ingredient.unit };
    if (sheet?.mode === 'new') {
      onChange([...items, { key: newKey(), quantity: 1, ...changes }]);
    } else if (sheet?.mode === 'edit') {
      update(sheet.key, changes);
    }
    setSheet(null);
  }

  return (
    <View style={styles.container}>
      {unknownCount > 0 && (
        <View style={styles.warning}>
          <Text style={styles.warningText}>
            Pozycji spoza słownika: {unknownCount}. Przepisy ich nie uwzględnią, więc przypisz je albo usuń.
          </Text>
        </View>
      )}

      {items.map((item) => {
        const ingredient = item.ingredient_id === null ? undefined : byId.get(item.ingredient_id);
        return (
          <Card key={item.key} style={item.ingredient_id === null && styles.unknownCard}>
            <View style={styles.rowTop}>
              <Pressable style={styles.names} onPress={() => setSheet({ mode: 'edit', key: item.key })} hitSlop={6}>
                <Text style={styles.label}>
                  {item.label} <Text style={styles.pencil}>✎</Text>
                </Text>
                {ingredient && ingredient.name_pl !== item.label && (
                  <Text style={styles.dictionary}>w słowniku: {ingredient.name_pl}</Text>
                )}
              </Pressable>
              <View style={styles.amount}>
                <QuantityInput value={item.quantity} onChange={(quantity) => update(item.key, { quantity })} />
                <Text style={styles.unit}>{UNIT_LABELS[item.unit]}</Text>
              </View>
            </View>

            <View style={styles.rowBottom}>
              <View style={styles.badges}>
                {item.ingredient_id === null && <Badge label="spoza słownika" tone="warning" />}
                {item.confidence === 'low' && <Badge label="niepewne" />}
                {ingredient?.custom && <Badge label="dodany" tone="info" />}
              </View>
              <Pressable onPress={() => setSheet({ mode: 'edit', key: item.key })} hitSlop={8}>
                <Text style={styles.action}>{item.ingredient_id === null ? 'Przypisz' : 'Zmień'}</Text>
              </Pressable>
              <Pressable onPress={() => remove(item.key)} hitSlop={8}>
                <Text style={[styles.action, styles.remove]}>Usuń</Text>
              </Pressable>
            </View>

            {showVisibility && (
              <View style={styles.visibility}>
                {VISIBILITY_OPTIONS.map((option) => {
                  const active = (item.visibility ?? 'visible') === option.value;
                  return (
                    <Pressable
                      key={option.value}
                      onPress={() => update(item.key, { visibility: option.value })}
                      style={[styles.visibilityOption, active && styles.visibilityActive]}
                    >
                      <Text style={[styles.visibilityText, active && styles.visibilityTextActive]}>{option.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
            )}
          </Card>
        );
      })}

      <AppButton
        title="+ Dodaj produkt"
        variant="secondary"
        onPress={() => setSheet({ mode: 'new' })}
        disabled={ingredients.length === 0}
      />

      {sheet && (
        <IngredientSheet
          title={sheet.mode === 'new' ? 'Dodaj produkt' : 'Co to jest?'}
          initialQuery={editedItem?.label ?? ''}
          defaultUnit={editedItem?.unit ?? 'pcs'}
          ingredients={ingredients}
          onPick={pick}
          onCreated={onIngredientCreated}
          onClose={() => setSheet(null)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
  },
  warning: {
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.warningSoft,
  },
  warningText: {
    color: colors.warning,
    fontSize: font.small,
  },
  unknownCard: {
    borderColor: colors.warningSoft,
    borderWidth: 2,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  names: {
    flex: 1,
    gap: 2,
  },
  label: {
    fontSize: font.body,
    fontWeight: '600',
    color: colors.text,
  },
  pencil: {
    color: colors.muted,
    fontWeight: '400',
  },
  dictionary: {
    fontSize: font.small,
    color: colors.muted,
  },
  amount: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  quantity: {
    width: 64,
    backgroundColor: colors.background,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    textAlign: 'right',
    fontSize: font.body,
    color: colors.text,
  },
  unit: {
    width: 30,
    color: colors.muted,
  },
  rowBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
  },
  badges: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  action: {
    color: colors.primary,
    fontWeight: '600',
  },
  remove: {
    color: colors.danger,
  },
  visibility: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  visibilityOption: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  visibilityActive: {
    backgroundColor: colors.infoSoft,
    borderColor: colors.info,
  },
  visibilityText: {
    fontSize: font.small,
    color: colors.muted,
  },
  visibilityTextActive: {
    color: colors.info,
    fontWeight: '600',
  },
});
