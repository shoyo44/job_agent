import { initializeApp, type FirebaseApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, type Auth } from 'firebase/auth'

type FirebaseRuntime = {
  app: FirebaseApp | null
  auth: Auth | null
  googleProvider: GoogleAuthProvider | null
  setupError: string
}

function buildRuntime(): FirebaseRuntime {
  const firebaseConfig = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID,
    measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
  }

  const missingRequired: string[] = []
  if (!firebaseConfig.apiKey) missingRequired.push('VITE_FIREBASE_API_KEY')
  if (!firebaseConfig.authDomain) missingRequired.push('VITE_FIREBASE_AUTH_DOMAIN')
  if (!firebaseConfig.projectId) missingRequired.push('VITE_FIREBASE_PROJECT_ID')
  if (!firebaseConfig.appId) missingRequired.push('VITE_FIREBASE_APP_ID')

  if (missingRequired.length > 0) {
    return {
      app: null,
      auth: null,
      googleProvider: null,
      setupError: `Missing Firebase env vars: ${missingRequired.join(', ')}`,
    }
  }

  try {
    const app = initializeApp(firebaseConfig)
    return {
      app,
      auth: getAuth(app),
      googleProvider: new GoogleAuthProvider(),
      setupError: '',
    }
  } catch (error) {
    return {
      app: null,
      auth: null,
      googleProvider: null,
      setupError: `Firebase init failed: ${String(error)}`,
    }
  }
}

const runtime = buildRuntime()

export const app = runtime.app
export const auth = runtime.auth
export const googleProvider = runtime.googleProvider
export const firebaseSetupError = runtime.setupError
