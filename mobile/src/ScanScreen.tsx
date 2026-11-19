import * as ImagePicker from 'expo-image-picker';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Button, Image, StyleSheet, Text, View } from 'react-native';

import { getIngredients, scanFridge, type IngredientOption, type Zone, type ZonePhoto } from './api';
import ItemsEditor, { toFridgeItems, type FridgeItem } from './ItemsEditor';

// Kolejność stref ze specyfikacji (D-001).
const STEPS: { zone: Zone; title: string }[] = [
  { zone: 'door', title: 'drzwi' },
  { zone: 'shelves_upper', title: 'półki górne' },
  { zone: 'shelves_lower', title: 'półki dolne' },
];

const PICKER_OPTIONS: ImagePicker.ImagePickerOptions = {
  mediaTypes: ['images'],
  quality: 0.7,
  // iOS: z galerii JPEG zamiast HEIC, którego backend (PIL) nie otworzy.
  preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible,
};

type Source = 'camera' | 'library';

export default function ScanScreen() {
  const [photos, setPhotos] = useState<ZonePhoto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<FridgeItem[] | null>(null);
  const [ingredients, setIngredients] = useState<IngredientOption[]>([]);

  // Słownik pobieramy raz, przy pierwszym pokazaniu ekranu. Bez niego działa skan,
  // tylko nie da się dodać produktu ani przypisać pozycji spoza słownika.
  useEffect(() => {
    getIngredients()
      .then((list) => setIngredients([...list].sort((a, b) => a.name_pl.localeCompare(b.name_pl, 'pl'))))
      .catch((caught) => setError(`Nie udało się pobrać słownika: ${caught instanceof Error ? caught.message : caught}`));
  }, []);

  const step = photos.length;
  const allTaken = step >= STEPS.length;

  async function addPhoto(source: Source) {
    setError(null);
    if (source === 'camera') {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        setError('Bez dostępu do aparatu nie zrobię zdjęcia. Włącz go w ustawieniach telefonu.');
        return;
      }
    }

    const picked =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync(PICKER_OPTIONS)
        : await ImagePicker.launchImageLibraryAsync(PICKER_OPTIONS);
    if (picked.canceled) {
      return;
    }

    const asset = picked.assets[0];
    setPhotos((previous) =>
      previous.length >= STEPS.length
        ? previous
        : [...previous, { zone: STEPS[previous.length].zone, uri: asset.uri }],
    );
  }

  async function analyze() {
    setLoading(true);
    setError(null);
    try {
      const result = await scanFridge(photos);
      setItems(toFridgeItems(result.items));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setPhotos([]);
    setItems(null);
    setError(null);
  }

  return (
    <View style={styles.container}>
      {allTaken ? (
        <Text style={styles.step}>Wszystkie strefy gotowe</Text>
      ) : (
        <>
          <Text style={styles.step}>
            Krok {step + 1}/{STEPS.length}: {STEPS[step].title}
          </Text>
          <Button title="Zrób zdjęcie" onPress={() => addPhoto('camera')} />
          <Button title="Z galerii" onPress={() => addPhoto('library')} />
        </>
      )}

      <View style={styles.thumbnails}>
        {photos.map((photo) => (
          <Image key={photo.zone} source={{ uri: photo.uri }} style={styles.thumbnail} />
        ))}
      </View>

      {step > 0 && !loading && !items && (
        <Button title="Usuń ostatnie zdjęcie" onPress={() => setPhotos((previous) => previous.slice(0, -1))} />
      )}

      {allTaken && !items && (
        <Button title={loading ? 'Analizuję…' : 'Analizuj'} onPress={analyze} disabled={loading} />
      )}
      {loading && <ActivityIndicator size="large" />}
      {error && <Text style={styles.error}>{error}</Text>}

      {items && (
        <View style={styles.result}>
          <Text style={styles.step}>Produkty w lodówce ({items.length})</Text>
          <ItemsEditor items={items} ingredients={ingredients} onChange={setItems} />
          <Button title="Nowy skan" onPress={reset} />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
    alignItems: 'center',
  },
  step: {
    fontSize: 18,
    fontWeight: '600',
  },
  thumbnails: {
    flexDirection: 'row',
    gap: 8,
  },
  thumbnail: {
    width: 80,
    height: 110,
    borderRadius: 6,
  },
  error: {
    color: '#c00',
    textAlign: 'center',
  },
  result: {
    gap: 6,
    alignSelf: 'stretch',
  },
});
