import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';

import '../api/providers.dart';
import '../widgets/profile_kit.dart';

/// Share as Template: the bot's `<name>.roost-bot.json` to the phone's share sheet.
Future<void> shareTemplate(
    BuildContext context, WidgetRef ref, String botId, String name) async {
  await attempt(context, () async {
    final file = await ref
        .read(apiClientProvider)
        .get('/api/bots/${Uri.encodeComponent(botId)}/template');
    final text = const JsonEncoder.withIndent('  ').convert(file);
    final slug = name.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-');
    await SharePlus.instance.share(ShareParams(
      text: text,
      subject: '$slug.roost-bot.json',
    ));
  });
}

/// Retire this bot, after the confirm; then back to Home.
Future<void> retireBot(
    BuildContext context, WidgetRef ref, String botId, String name) async {
  final ok = await confirm(
    context,
    'Retire $name?',
    'Retire this bot',
    body: 'Its chat and everything it made are removed. This cannot be undone.',
  );
  if (!ok || !context.mounted) return;
  final done = await attempt(
      context,
      () => ref
          .read(apiClientProvider)
          .delete('/api/bots/${Uri.encodeComponent(botId)}'));
  if (done && context.mounted) context.go('/');
}
