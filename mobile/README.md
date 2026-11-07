# Radhe AI Assistant — Android Companion Application Architecture

This directory contains the production-grade Android companion client for Radhe Personal AI Assistant.

## 1. Overview & Capabilities
- **Voice Assistant**: One-touch push-to-talk voice recording, streaming directly to Radhe's FastAPI REST & WebSocket backend (`/api/v1/chat`).
- **WhatsApp Approval Deck**: Live cards for staged WhatsApp drafts awaiting approval, with one-tap "Approve & Send" and "Discard" actions.
- **Morning Daily Briefing Widget**: Displays today's agenda, weather, pending high-priority tasks, and hydration goals.
- **Biometric Security**: Android `BiometricPrompt` (Fingerprint / Face Unlock) to unlock the app before accessing sensitive memories or settings.
- **Background Synchronization**: Powered by Android Jetpack `WorkManager`, syncing tasks, reminders, and health vitals periodically even when the app is in background.

---

## 2. Directory Layout
```
mobile/
├── README.md                          # Architecture and setup guide
└── android/
    ├── AndroidManifest.xml            # Permissions and service declarations
    ├── RadheApiService.kt             # Retrofit REST interface for /api/v1/
    ├── MainActivity.kt                # Jetpack Compose UI with Voice, Briefing & Approvals
    ├── VoiceRecorder.kt               # Audio recording & PCM/WAV speech capture
    └── SyncWorker.kt                  # Background synchronization CoroutineWorker
```

---

## 3. Build & Setup Instructions
1. Open the `mobile/android/` directory in Android Studio (Koala / Ladybug or newer).
2. Configure `gradle.properties` or `app/build.gradle.kts`:
   - `minSdk = 26` (Android 8.0 Oreo)
   - `targetSdk = 35` (Android 15)
   - Add dependencies:
     - `androidx.compose.ui:ui`
     - `com.squareup.retrofit2:retrofit:2.11.0`
     - `com.squareup.retrofit2:converter-gson:2.11.0`
     - `androidx.work:work-runtime-ktx:2.9.0`
     - `androidx.biometric:biometric:1.2.0-alpha05`
3. Point `BASE_URL` in `RadheApiService.kt` to your Radhe desktop/server instance:
   - For local emulator: `http://10.0.2.2:8000/api/v1/`
   - For physical device on same WiFi: `http://<YOUR_PC_IP>:8000/api/v1/`
