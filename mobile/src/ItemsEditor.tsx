import { useMemo, useState } from 'react';
import { Button, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { Confidence, DetectedItem, IngredientOption, Unit } from './api';
import IngredientPicker from './IngredientPicker';

// Pozycja na ekranie korekty. Kształt jak DetectedItem; confidence nie ma, gdy dodano ją ręcznie (D-009).
export type FridgeItem = {
  key: string;
  ingredient_id: string | null;
  label: string;
  quantity: number;
  unit: Unit;
  confidence?: Confidence;
};

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
};

export default function ItemsEditor({ items, ingredients, onChange }: Props) {
  // null: wybór zamknięty, 'new': dodawanie produktu, inaczej key pozycji, której zmieniamy składnik.
  const [picking, setPicking] = useState<string | null>(null);

  const namesById = useMemo(
    () => new Map(ingredients.map((ingredient) => [ingredient.id, ingredient.name_pl])),
    [ingredients],
  );
  const unknownCount = items.filter((item) => item.ingredient_id === null).length;

  function update(key: string, changes: Partial<FridgeItem>) {
    onChange(items.map((item) => (item.key === key ? { ...item, ...changes } : item)));
  }

  function remove(key: string) {
    onChange(items.filter((item) => item.key !== key));
  }

  function pick(ingredient: IngredientOption) {
    if (picking === 'new') {
      onChange([
        ...items,
        { key: newKey(), ingredient_id: ingredient.id, label: ingredient.name_pl, quantity: 1, unit: ingredient.unit },
      ]);
    } else if (picking !== null) {
      update(picking, { ingredient_id: ingredient.id, unit: ingredient.unit });
    }
    setPicking(null);
  }

  return (
    <View style={styles.container}>
      {items.map((item) => (
        <View key={item.key} style={styles.row}>
          <View style={styles.rowTop}>
            <Text style={styles.label}>{item.label}</Text>
            <QuantityInput value={item.quantity} onChange={(quantity) => update(item.key, { quantity })} />
            <Text style={styles.unit}>{UNIT_LABELS[item.unit]}</Text>
          </View>
          <View style={styles.rowBottom}>
            <Text style={item.ingredient_id === null ? styles.unknown : styles.dictionary}>
              {item.ingredient_id === null
                ? 'spoza słownika'
                : `słownik: ${namesById.get(item.ingredient_id) ?? item.ingredient_id}`}
            </Text>
            <Pressable onPress={() => setPicking(item.key)}>
              <Text style={styles.action}>{item.ingredient_id === null ? 'Przypisz' : 'Zmień'}</Text>
            </Pressable>
            <Pressable onPress={() => remove(item.key)}>
              <Text style={[styles.action, styles.remove]}>Usuń</Text>
            </Pressable>
          </View>
          {picking === item.key && (
            <IngredientPicker ingredients={ingredients} onPick={pick} onCancel={() => setPicking(null)} />
          )}
        </View>
      ))}

      {unknownCount > 0 && (
        <Text style={styles.unknown}>
          Pozycji spoza słownika: {unknownCount}. Przepisy ich nie uwzględnią, więc przypisz je albo usuń.
        </Text>
      )}

      {picking === 'new' ? (
        <IngredientPicker ingredients={ingredients} onPick={pick} onCancel={() => setPicking(null)} />
      ) : (
        <Button title="Dodaj produkt" onPress={() => setPicking('new')} disabled={ingredients.length === 0} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    gap: 10,
  },
  row: {
    gap: 4,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rowBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  label: {
    flex: 1,
    fontSize: 16,
  },
  quantity: {
    width: 64,
    borderWidth: 1,
    borderColor: '#999',
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 6,
    textAlign: 'right',
  },
  unit: {
    width: 28,
  },
  dictionary: {
    flex: 1,
    color: '#666',
  },
  unknown: {
    flex: 1,
    color: '#b45309',
  },
  action: {
    color: '#2563eb',
  },
  remove: {
    color: '#c00',
  },
});
