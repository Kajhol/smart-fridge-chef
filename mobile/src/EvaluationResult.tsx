import { StyleSheet, Text, View } from 'react-native';

import type { SavedScan } from './api';
import { colors, font, radius, spacing } from './theme';
import { Badge, Card } from './ui';

function percent(value: number | null): string {
  return value === null ? '–' : `${Math.round(value * 100)}%`;
}

type Props = {
  saved: SavedScan;
  namesById: Map<string, string>;
};

// Wynik POST /scans: jak dobrze model rozpoznał ten skan w porównaniu z poprawioną listą (D-003).
export default function EvaluationResult({ saved, namesById }: Props) {
  const { metrics } = saved;
  const names = (ids: string[]) => ids.map((id) => namesById.get(id) ?? id).join(', ') || '–';

  return (
    <Card>
      <View style={styles.header}>
        <Text style={styles.title}>Zapisano skan</Text>
        <Badge label={saved.scan_id} tone="success" />
      </View>

      <View style={styles.tiles}>
        <Tile label="Recall" value={percent(metrics.recall)} hint="ile model znalazł" />
        <Tile label="Precision" value={percent(metrics.precision)} hint="ile nie zmyślił" />
        <Tile label="F1" value={metrics.f1 === null ? '–' : metrics.f1.toFixed(2)} hint="razem" />
      </View>

      <Text style={styles.text}>
        Znalezione {metrics.found} z {metrics.expected} produktów ze słownika. Recall bez schowanych:{' '}
        {percent(metrics.recall_seen)}.
      </Text>
      <Row label="Pominięte" value={names(metrics.missed)} />
      <Row label="Halucynacje" value={names(metrics.hallucinations)} />
      <Row label="Duplikaty" value={names(metrics.duplicates)} />
      {metrics.unknown_expected > 0 && (
        <Text style={styles.small}>Spoza słownika (poza metrykami): {metrics.unknown_expected}.</Text>
      )}
      <Text style={styles.small}>
        Na laptopie: data/scans/{saved.scan_id}. Plik ground_truth.json można jeszcze poprawić ręcznie.
      </Text>
    </Card>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <View style={styles.tile}>
      <Text style={styles.tileValue}>{value}</Text>
      <Text style={styles.tileLabel}>{label}</Text>
      <Text style={styles.tileHint}>{hint}</Text>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Text style={styles.text}>
      <Text style={styles.rowLabel}>{label}: </Text>
      {value}
    </Text>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    fontSize: font.heading,
    fontWeight: '700',
    color: colors.text,
  },
  tiles: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  tile: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
  },
  tileValue: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.primary,
  },
  tileLabel: {
    fontSize: font.small,
    fontWeight: '600',
    color: colors.text,
  },
  tileHint: {
    fontSize: 11,
    color: colors.muted,
  },
  text: {
    fontSize: font.body,
    color: colors.text,
  },
  rowLabel: {
    fontWeight: '600',
  },
  small: {
    fontSize: font.small,
    color: colors.muted,
  },
});
