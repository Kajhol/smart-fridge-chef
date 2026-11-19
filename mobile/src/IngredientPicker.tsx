import { useState } from 'react';
import { Button, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { IngredientOption } from './api';

const MAX_RESULTS = 8;

// "Jabłko" i "jablko" mają pasować do siebie: małe litery, bez ogonków.
function simplify(text: string): string {
  return text
    .toLowerCase()
    .replace(/ł/g, 'l')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

type Props = {
  ingredients: IngredientOption[];
  onPick: (ingredient: IngredientOption) => void;
  onCancel: () => void;
};

export default function IngredientPicker({ ingredients, onPick, onCancel }: Props) {
  const [query, setQuery] = useState('');

  const needle = simplify(query.trim());
  const matches = needle
    ? ingredients.filter((ingredient) => simplify(ingredient.name_pl).includes(needle)).slice(0, MAX_RESULTS)
    : [];

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        placeholder="Szukaj w słowniku, np. ser"
        value={query}
        onChangeText={setQuery}
        autoFocus
      />
      {matches.map((ingredient) => (
        <Pressable key={ingredient.id} style={styles.option} onPress={() => onPick(ingredient)}>
          <Text>{ingredient.name_pl}</Text>
        </Pressable>
      ))}
      {needle !== '' && matches.length === 0 && <Text style={styles.hint}>Nie ma tego w słowniku</Text>}
      <Button title="Anuluj" onPress={onCancel} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    gap: 4,
    padding: 8,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
  },
  input: {
    borderWidth: 1,
    borderColor: '#999',
    borderRadius: 6,
    padding: 8,
  },
  option: {
    paddingVertical: 8,
    paddingHorizontal: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  hint: {
    color: '#666',
  },
});
