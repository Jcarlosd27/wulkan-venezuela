import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';

import '../config/mobile_environment.dart';

Future<void> configureMobileRuntime() async {
  if (!mobileEnvironment.usesFirestore && !mobileEnvironment.usesFirebaseAuth) {
    return;
  }

  if (mobileEnvironment.firestoreEmulatorHost.isNotEmpty) {
    await Firebase.initializeApp(
      options: FirebaseOptions(
        apiKey: const String.fromEnvironment(
          "WULKAN_FIREBASE_API_KEY",
          defaultValue: "demo-api-key",
        ),
        appId: const String.fromEnvironment(
          "WULKAN_FIREBASE_APP_ID",
          defaultValue: "1:1234567890:android:wulkanlocal",
        ),
        messagingSenderId: const String.fromEnvironment(
          "WULKAN_FIREBASE_MESSAGING_SENDER_ID",
          defaultValue: "1234567890",
        ),
        projectId: mobileEnvironment.projectId,
      ),
    );
  } else {
    await Firebase.initializeApp();
  }

  if (mobileEnvironment.usesFirestore &&
      mobileEnvironment.firestoreEmulatorHost.isNotEmpty) {
    final emulator = _parseHostPort(mobileEnvironment.firestoreEmulatorHost);
    FirebaseFirestore.instance
        .useFirestoreEmulator(emulator.host, emulator.port);
  }
}

({String host, int port}) _parseHostPort(String value) {
  final parts = value.split(":");
  final host =
      parts.isNotEmpty && parts.first.isNotEmpty ? parts.first : "10.0.2.2";
  final port = parts.length > 1 ? int.tryParse(parts[1]) ?? 8085 : 8085;

  return (host: host, port: port);
}
