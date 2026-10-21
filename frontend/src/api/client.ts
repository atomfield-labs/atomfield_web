import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';

const API_BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Device Fingerprinting
client.interceptors.request.use((config) => {
  let deviceId = localStorage.getItem('atomfield_device_id');
  if (!deviceId) {
    deviceId = uuidv4();
    localStorage.setItem('atomfield_device_id', deviceId);
  }
  
  config.headers['X-Anonymous-Id'] = deviceId;
  
  const apiKey = localStorage.getItem('atomfield_api_key');
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  
  return config;
});

export default client;
