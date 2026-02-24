# SolverLife Hosting Setup (GitHub Pages + Firebase)

## 1) Publish on GitHub Pages
1. Push this project to a GitHub repo.
2. In GitHub: `Settings -> Pages`.
3. Source: `Deploy from a branch`.
4. Branch: `main` (or your branch), folder: `/ (root)`.

## 2) Enable Firebase (real online users)
1. Create a Firebase project at https://console.firebase.google.com.
2. Enable:
- Authentication -> Sign-in method -> Email/Password
- Firestore Database (production mode)
- Storage
3. Register a Web App in Firebase and copy config.
4. In `Paper2solver.html`, fill `FIREBASE_CONFIG` with your values.

## 3) Firestore rules (minimum)
Use these rules in Firebase Firestore Rules:

```txt
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
      match /history/{docId} {
        allow read, write: if request.auth != null && request.auth.uid == userId;
      }
    }

    match /stats/{userId} {
      allow read: if true;
      allow write: if request.auth != null && request.auth.uid == userId;
    }

    match /reports/{docId} {
      allow create: if request.auth != null;
      allow read: if false;
      allow update, delete: if false;
    }
  }
}
```

## 4) Storage rules (minimum)
Use these in Firebase Storage Rules:

```txt
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /reports/{userId}/{allPaths=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

## 5) Notes
- If Firebase config is empty, app runs in local mode.
- Leaderboard has no fake users; only real `stats` docs are shown.
- Login mail feature is removed.
- Captcha is client-side verification for bot friction.
