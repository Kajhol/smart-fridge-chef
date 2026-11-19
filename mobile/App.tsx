import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Button, ScrollView, StyleSheet, Text } from 'react-native';

import { checkHealth } from './src/api';
import ScanScreen from './src/ScanScreen';

export default function App() {
  const [status, setStatus] = useState('Nie sprawdzono');

  async function onCheck() {
    setStatus('Łączę…');
    try {
      const health = await checkHealth();
      setStatus(`OK, model: ${health.model}`);
    } catch (error) {
      setStatus(`Błąd: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>Smart Fridge Chef</Text>
      <Button title="Sprawdź backend" onPress={onCheck} />
      <Text>{status}</Text>
      <ScanScreen />
      <StatusBar style="auto" />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingTop: 64,
    paddingHorizontal: 20,
    paddingBottom: 40,
    alignItems: 'center',
    gap: 16,
    backgroundColor: '#fff',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
  },
});
