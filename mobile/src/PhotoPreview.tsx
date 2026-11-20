import { Image, Modal, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { font, spacing } from './theme';
import { AppButton } from './ui';

type Props = {
  title: string;
  uri: string;
  onRetake: () => void;
  onPickFromLibrary: () => void;
  onClose: () => void;
};

export default function PhotoPreview({ title, uri, onRetake, onPickFromLibrary, onClose }: Props) {
  return (
    <Modal visible animationType="fade" onRequestClose={onClose}>
      <SafeAreaProvider>
        <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
          <Text style={styles.title}>{title}</Text>
          {/* contain: całe zdjęcie na ekranie, bez przycinania brzegów. */}
          <Image source={{ uri }} style={styles.photo} resizeMode="contain" />
          <View style={styles.actions}>
            <View style={styles.row}>
              <AppButton title="Zrób ponownie" onPress={onRetake} style={styles.grow} />
              <AppButton title="Z galerii" variant="secondary" onPress={onPickFromLibrary} style={styles.grow} />
            </View>
            <AppButton title="Zamknij" variant="secondary" onPress={onClose} />
          </View>
        </SafeAreaView>
      </SafeAreaProvider>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#000',
  },
  title: {
    color: '#fff',
    fontSize: font.heading,
    fontWeight: '700',
    textAlign: 'center',
    paddingVertical: spacing.md,
  },
  photo: {
    flex: 1,
  },
  actions: {
    gap: spacing.sm,
    padding: spacing.lg,
  },
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  grow: {
    flex: 1,
  },
});
