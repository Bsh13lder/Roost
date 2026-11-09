import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:timezone/timezone.dart' as tz;

import '../theme/tokens.dart';
import '../util/app_time.dart';
import '../widgets/profile_kit.dart';

/// "Only run when the page changes" (owner, 2026-11-04): Roost reads the page
/// itself every few minutes and runs the routine only when that part changed.
const watchLabel = 'Only run when the page changes';
const watchHint =
    'Roost reads the page itself, with no model, and runs this routine only when that part changed.';
const watchMinMinutes = 5; // the server's WATCH_EVERY_MIN_MINUTES
const watchDefaultMinutes = 5;

/// What Save sends for the watch: null when it is off (the server checks the
/// address and the minutes, and answers in plain words).
Map<String, dynamic>? watchBody(
    {required bool on, required String url, required String part, required String every}) {
  if (!on) return null;
  return {
    'url': url.trim(),
    'part': part.trim(),
    'every_min': int.tryParse(every.trim()) ?? watchDefaultMinutes,
  };
}

/// "14:50" when [iso] is today on the account's clock, else "Mon 2 Nov 14:50"; "" for none.
String appChangeTime(String? iso, DateTime now) {
  if (iso == null || iso.isEmpty) return '';
  final DateTime when;
  try {
    when = parseServerTime(iso);
  } on FormatException {
    return '';
  }
  final local = tz.TZDateTime.from(when, appLocation());
  final today = appDay(when) == appDay(now);
  return DateFormat(today ? 'HH:mm' : 'EEE d MMM HH:mm').format(local);
}

/// "Watching web.whatsapp.com · every 5 min · last change 14:50" for a
/// watching routine; "" for any other.
String watchLine(Map<String, dynamic> routine, DateTime now) {
  final watch = routine['watch'];
  if (watch is! Map) return '';
  final head = 'Watching ${watch['host'] ?? ''} · every ${watch['every_min'] ?? ''} min';
  final changed = appChangeTime(watch['last_changed_at'] as String?, now);
  return changed.isEmpty ? head : '$head · last change $changed';
}

/// The switch, the page's address, the part in plain words and how often.
class WatchFields extends StatelessWidget {
  const WatchFields({
    super.key,
    required this.on,
    required this.onChanged,
    required this.url,
    required this.part,
    required this.every,
  });

  final bool on;
  final ValueChanged<bool> onChanged;
  final TextEditingController url;
  final TextEditingController part;
  final TextEditingController every;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SwitchListTile(
        key: const Key('routine-watch'),
        contentPadding: EdgeInsets.zero,
        title: const Text(watchLabel),
        value: on,
        onChanged: onChanged,
      ),
      if (on) ...[
        const Quiet(watchHint),
        const SizedBox(height: Tokens.space2),
        TextField(
            key: const Key('routine-watch-url'),
            controller: url,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
                labelText: 'Page address', hintText: 'https://web.whatsapp.com')),
        const SizedBox(height: Tokens.space3),
        TextField(
            key: const Key('routine-watch-part'),
            controller: part,
            decoration: const InputDecoration(
                labelText: 'What part to watch',
                hintText: 'the physio chat',
                helperText: 'In plain words. Empty: the whole page.')),
        const SizedBox(height: Tokens.space3),
        TextField(
            key: const Key('routine-watch-every'),
            controller: every,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
                labelText: 'Check every (minutes)',
                helperText: 'At least $watchMinMinutes minutes.')),
      ],
    ]);
  }
}
