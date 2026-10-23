import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';

export const API_BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Headers that identify this browser (device fingerprint) and its
 * user (API key). Shared by axios and the live event stream, which
 * uses fetch.
 */
export function authHeaders(): Record<string, string> {
  let deviceId = localStorage.getItem('atomfield_device_id');
  if (!deviceId) {
    deviceId = uuidv4();
    localStorage.setItem('atomfield_device_id', deviceId);
  }
  const headers: Record<string, string> = { 'X-Anonymous-Id': deviceId };
  const apiKey = localStorage.getItem('atomfield_api_key');
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  return headers;
}

client.interceptors.request.use((config) => {
  for (const [name, value] of Object.entries(authHeaders())) {
    config.headers[name] = value;
  }
  return config;
});

export default client;
