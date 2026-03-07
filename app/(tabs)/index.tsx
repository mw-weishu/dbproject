import { Text, View } from '@/components/Themed';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, TextInput, TouchableOpacity } from 'react-native';

const API_BASE = '/api/example';

export default function TabOneScreen() {
  const [response, setResponse] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [echoText, setEchoText] = useState('Hello Vercel!');
  const [mathA, setMathA] = useState('10');
  const [mathB, setMathB] = useState('3');

  const callApi = async (url: string) => {
    setLoading(true);
    setResponse('');
    try {
      const res = await fetch(url);
      const data = await res.json();
      setResponse(JSON.stringify(data, null, 2));
    } catch (err: any) {
      setResponse(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Python API Tester</Text>
      <View style={styles.separator} lightColor="#eee" darkColor="rgba(255,255,255,0.1)" />

      {/* Hello Button */}
      <TouchableOpacity
        style={[styles.button, { backgroundColor: '#4CAF50' }]}
        onPress={() => callApi(`${API_BASE}?action=hello`)}
      >
        <Text style={styles.buttonText}>👋 Say Hello</Text>
      </TouchableOpacity>

      {/* Time Button */}
      <TouchableOpacity
        style={[styles.button, { backgroundColor: '#2196F3' }]}
        onPress={() => callApi(`${API_BASE}?action=time`)}
      >
        <Text style={styles.buttonText}>🕐 Get Server Time</Text>
      </TouchableOpacity>

      {/* Echo Section */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={echoText}
          onChangeText={setEchoText}
          placeholder="Text to echo..."
          placeholderTextColor="#999"
        />
      </View>
      
        <TouchableOpacity
          style={[styles.button, { backgroundColor: '#FF9800' }]}
          onPress={() => callApi(`${API_BASE}?action=echo&text=${encodeURIComponent(echoText)}`)}
        >
          <Text style={styles.buttonText}>🔁 Echo</Text>
        </TouchableOpacity>

      {/* Math Section */}
      <View style={styles.inputRow}>
        <TextInput
          style={[styles.input, styles.smallInput]}
          value={mathA}
          onChangeText={setMathA}
          placeholder="A"
          keyboardType="numeric"
          placeholderTextColor="#999"
        />
        <TextInput
          style={[styles.input, styles.smallInput]}
          value={mathB}
          onChangeText={setMathB}
          placeholder="B"
          keyboardType="numeric"
          placeholderTextColor="#999"
        />
      </View>
      
        <TouchableOpacity
          style={[styles.button, { backgroundColor: '#9C27B0' }]}
          onPress={() => callApi(`${API_BASE}?action=math&a=${mathA}&b=${mathB}`)}
        >
          <Text style={styles.buttonText}>🧮 Math</Text>
        </TouchableOpacity>

      {/* Response Area */}
      {loading && <ActivityIndicator size="large" color="#2196F3" style={{ marginTop: 20 }} />}
      {response !== '' && (
        <View style={styles.responseBox}>
          <Text style={styles.responseLabel}>Response:</Text>
          <Text style={styles.responseText}>{response}</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    alignItems: 'center',
    paddingVertical: 30,
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
  },
  separator: {
    marginVertical: 20,
    height: 1,
    width: '80%',
  },
  button: {
    paddingVertical: 14,
    paddingHorizontal: 28,
    borderRadius: 10,
    marginVertical: 6,
    width: '100%',
    maxWidth: 350,
    alignItems: 'center',
  },
  smallButton: {
    width: 'auto',
    flex: 0,
    paddingHorizontal: 16,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginVertical: 6,
    width: '100%',
    maxWidth: 350,
    backgroundColor: 'transparent',
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
    backgroundColor: '#f9f9f9',
  },
  smallInput: {
    flex: 0.4,
  },
  responseBox: {
    marginTop: 20,
    padding: 16,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ddd',
    width: '100%',
    maxWidth: 350,
    backgroundColor: '#1e1e1e',
  },
  responseLabel: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 8,
    color: '#aaa',
  },
  responseText: {
    fontFamily: 'monospace',
    fontSize: 13,
    color: '#4FC3F7',
  },
});
