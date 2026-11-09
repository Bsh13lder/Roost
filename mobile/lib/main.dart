import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

void main() {
  // The app and the Stay connected service talk over this port.
  FlutterForegroundTask.initCommunicationPort();
  runApp(const ProviderScope(child: RoostApp()));
}
