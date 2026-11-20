import * as ImagePicker from 'expo-image-picker';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  getIngredients,
  saveScan,
  scanFridge,
  type IngredientOption,
  type SavedScan,
  type ScanResult,
  type Zone,
  type ZonePhoto,
} from './api';
import EvaluationResult from './EvaluationResult';
import ItemsEditor, { toFridgeItems, type FridgeItem } from './ItemsEditor';
import PhotoPreview from './PhotoPreview';
import { DEFAULT_PROFILE } from './profile';
import RecipesSection from './RecipesSection';
import { colors, font, radius, spacing } from './theme';
import { AppButton, Card, StepProgress } from './ui';

// Kolejność stref ze specyfikacji (D-001).
const STEPS: { zone: Zone; title: string; hint: string }[] = [
  { zone: 'door', title: 'Drzwi', hint: 'Otwórz lodówkę i sfotografuj półki na drzwiach.' },
  { zone: 'shelves_upper', title: 'Półki górne', hint: 'Zrób zdjęcie górnych półek, tak żeby było widać etykiety.' },
  { zone: 'shelves_lower', title: 'Półki dolne', hint: 'Na koniec dolne półki. Jeśli możesz, wysuń szufladę.' },
];

const PICKER_OPTIONS: ImagePicker.ImagePickerOptions = {
  mediaTypes: ['images'],
  quality: 0.7,
  // iOS: z galerii JPEG zamiast HEIC, którego backend (PIL) nie otworzy.
  preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible,
};

type Source = 'camera' | 'library';

function sortByName(list: IngredientOption[]): IngredientOption[] {
  return [...list].sort((a, b) => a.name_pl.localeCompare(b.name_pl, 'pl'));
}

export default function ScanScreen() {
  const [photos, setPhotos] = useState<ZonePhoto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<FridgeItem[] | null>(null);
  const [ingredients, setIngredients] = useState<IngredientOption[]>([]);
  const [preview, setPreview] = useState<Zone | null>(null);
  // Odpowiedź modelu bez poprawek i czas analizy: potrzebne do metryk przy zapisie do ewaluacji.
  const [prediction, setPrediction] = useState<ScanResult | null>(null);
  const [scanSeconds, setScanSeconds] = useState<number | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<SavedScan | null>(null);

  const namesById = useMemo(
    () => new Map(ingredients.map((ingredient) => [ingredient.id, ingredient.name_pl])),
    [ingredients],
  );

  // Słownik pobieramy raz, przy pierwszym pokazaniu ekranu. Bez niego działa skan,
  // tylko nie da się dodać produktu ani przypisać pozycji spoza słownika.
  useEffect(() => {
    getIngredients()
      .then((list) => setIngredients(sortByName(list)))
      .catch((caught) =>
        setError(`Nie udało się pobrać słownika: ${caught instanceof Error ? caught.message : caught}`),
      );
  }, []);

  const step = photos.length;
  const previewPhoto = photos.find((photo) => photo.zone === preview);
  const allTaken = step >= STEPS.length;

  // Zwraca uri zdjęcia albo null, gdy użytkownik anulował lub nie dał dostępu do aparatu.
  async function pickPhoto(source: Source): Promise<string | null> {
    setError(null);
    if (source === 'camera') {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        setError('Bez dostępu do aparatu nie zrobię zdjęcia. Włącz go w ustawieniach telefonu.');
        return null;
      }
    }

    const picked =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync(PICKER_OPTIONS)
        : await ImagePicker.launchImageLibraryAsync(PICKER_OPTIONS);
    return picked.canceled ? null : picked.assets[0].uri;
  }

  async function addPhoto(source: Source) {
    const uri = await pickPhoto(source);
    if (!uri) {
      return;
    }
    setPhotos((previous) =>
      previous.length >= STEPS.length ? previous : [...previous, { zone: STEPS[previous.length].zone, uri }],
    );
  }

  // Z podglądu: nowe zdjęcie tej samej strefy w miejsce starego. Podgląd zostaje otwarty i pokazuje nowe.
  async function replacePhoto(zone: Zone, source: Source) {
    const uri = await pickPhoto(source);
    if (!uri) {
      return;
    }
    setPhotos((previous) => previous.map((photo) => (photo.zone === zone ? { zone, uri } : photo)));
  }

  function onIngredientCreated(ingredient: IngredientOption) {
    setIngredients((previous) =>
      previous.some((item) => item.id === ingredient.id) ? previous : sortByName([...previous, ingredient]),
    );
  }

  async function save() {
    if (!items || !prediction) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const truthItems = items.map(({ ingredient_id, label, quantity, unit, visibility }) => ({
        ingredient_id,
        label,
        quantity,
        unit,
        visibility: visibility ?? 'visible',
      }));
      setSaved(await saveScan(photos, prediction, truthItems, scanSeconds));
      setEvaluating(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  async function analyze() {
    setLoading(true);
    setError(null);
    const started = Date.now();
    try {
      const result = await scanFridge(photos);
      setScanSeconds(Math.round((Date.now() - started) / 100) / 10);
      setPrediction(result);
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
    setPrediction(null);
    setScanSeconds(null);
    setEvaluating(false);
    setSaved(null);
    setError(null);
  }

  return (
    <View style={styles.container}>
      {!items && (
        <Card>
          <StepProgress labels={STEPS.map((s) => s.title)} current={step} />
          {allTaken ? (
            <View style={styles.stepText}>
              <Text style={styles.heading}>Wszystkie strefy gotowe</Text>
              <Text style={styles.hint}>Dotknij miniatury, żeby obejrzeć zdjęcie albo zrobić je ponownie.</Text>
            </View>
          ) : (
            <>
              <View style={styles.stepText}>
                <Text style={styles.kicker}>
                  Krok {step + 1} z {STEPS.length}
                </Text>
                <Text style={styles.heading}>{STEPS[step].title}</Text>
                <Text style={styles.hint}>{STEPS[step].hint}</Text>
              </View>
              <View style={styles.row}>
                <AppButton title="Zrób zdjęcie" onPress={() => addPhoto('camera')} style={styles.grow} />
                <AppButton
                  title="Z galerii"
                  variant="secondary"
                  onPress={() => addPhoto('library')}
                  style={styles.grow}
                />
              </View>
            </>
          )}

          <View style={styles.thumbnails}>
            {STEPS.map(({ zone, title }) => {
              const photo = photos.find((p) => p.zone === zone);
              return (
                <View key={zone} style={styles.thumbnailBox}>
                  {photo ? (
                    <Pressable onPress={() => setPreview(zone)} disabled={loading}>
                      <Image source={{ uri: photo.uri }} style={styles.thumbnail} />
                    </Pressable>
                  ) : (
                    <View style={[styles.thumbnail, styles.thumbnailEmpty]} />
                  )}
                  <Text style={styles.thumbnailLabel}>{title}</Text>
                </View>
              );
            })}
          </View>

          {step > 0 && !loading && (
            <AppButton
              title="Usuń ostatnie zdjęcie"
              variant="ghost"
              onPress={() => setPhotos((previous) => previous.slice(0, -1))}
            />
          )}

          {allTaken && (
            <AppButton title={loading ? 'Analizuję…' : 'Analizuj zdjęcia'} onPress={analyze} loading={loading} />
          )}
        </Card>
      )}

      {loading && (
        <Card style={styles.loadingCard}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.hint}>Model ogląda zdjęcia. Zwykle trwa to kilka sekund.</Text>
        </Card>
      )}

      {error && (
        <Card style={styles.errorCard}>
          <Text style={styles.errorText}>{error}</Text>
        </Card>
      )}

      {items && (
        <>
          <View style={styles.resultHeader}>
            <Text style={styles.heading}>Produkty w lodówce</Text>
            <Text style={styles.hint}>
              Znaleziono {items.length}. Popraw ilości i nazwy, zanim poszukamy przepisów.
            </Text>
          </View>
          <ItemsEditor
            items={items}
            ingredients={ingredients}
            onChange={setItems}
            onIngredientCreated={onIngredientCreated}
            showVisibility={evaluating}
          />

          {!evaluating && <RecipesSection items={items} profile={DEFAULT_PROFILE} />}

          {saved ? (
            <EvaluationResult saved={saved} namesById={namesById} />
          ) : (
            <Card>
              <Text style={styles.heading}>Ewaluacja rozpoznawania</Text>
              {evaluating ? (
                <>
                  <Text style={styles.hint}>
                    Lista po korekcie stanie się wzorcem, z którym porównamy model. Sprawdź ją przy otwartej lodówce:
                  </Text>
                  <Text style={styles.hint}>• przy każdym produkcie zaznacz, czy widać go na zdjęciach</Text>
                  <Text style={styles.hint}>
                    • dopisz produkty schowane (np. w szufladzie) i oznacz je jako „schowane”
                  </Text>
                  <Text style={styles.hint}>• ilości przepisz z opakowań, nie zgaduj ze zdjęć</Text>
                  <AppButton title="Zapisz skan" onPress={save} loading={saving} />
                  <AppButton title="Anuluj" variant="ghost" onPress={() => setEvaluating(false)} disabled={saving} />
                </>
              ) : (
                <>
                  <Text style={styles.hint}>
                    Zapisz ten skan do zbioru testowego (D-003): zdjęcia i poprawiona lista trafią na laptopa, a model
                    dostanie ocenę.
                  </Text>
                  <AppButton
                    title="Przygotuj zapis do ewaluacji"
                    variant="secondary"
                    onPress={() => setEvaluating(true)}
                  />
                </>
              )}
            </Card>
          )}

          <AppButton title="Nowy skan" variant="secondary" onPress={reset} />
        </>
      )}

      {previewPhoto && (
        <PhotoPreview
          title={STEPS.find((s) => s.zone === previewPhoto.zone)?.title ?? previewPhoto.zone}
          uri={previewPhoto.uri}
          onRetake={() => replacePhoto(previewPhoto.zone, 'camera')}
          onPickFromLibrary={() => replacePhoto(previewPhoto.zone, 'library')}
          onClose={() => setPreview(null)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.lg,
  },
  stepText: {
    gap: spacing.xs,
  },
  kicker: {
    fontSize: font.small,
    fontWeight: '600',
    color: colors.primary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
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
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  grow: {
    flex: 1,
  },
  thumbnails: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  thumbnailBox: {
    flex: 1,
    gap: spacing.xs,
  },
  thumbnail: {
    width: '100%',
    aspectRatio: 3 / 4,
    borderRadius: radius.sm,
    backgroundColor: colors.background,
  },
  thumbnailEmpty: {
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: colors.border,
  },
  thumbnailLabel: {
    fontSize: font.small,
    color: colors.muted,
    textAlign: 'center',
  },
  loadingCard: {
    alignItems: 'center',
  },
  errorCard: {
    backgroundColor: colors.dangerSoft,
    borderColor: colors.dangerSoft,
  },
  errorText: {
    color: colors.danger,
    fontSize: font.body,
  },
  resultHeader: {
    gap: spacing.xs,
  },
});
