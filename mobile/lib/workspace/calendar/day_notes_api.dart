import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/providers.dart';

/// One day note on the calendars (`DayNoteOut`).
class DayNote {
  const DayNote({required this.id, required this.day, required this.text, this.botName});

  factory DayNote.fromJson(Map<String, dynamic> j) => DayNote(
        id: j['id'] as String,
        day: DateTime.parse('${j['day']}T00:00:00Z'),
        text: j['text'] as String? ?? '',
        botName: j['bot_name'] as String?,
      );

  final String id;
  final DateTime day;
  final String text;
  final String? botName;
}

/// `GET/POST/DELETE /api/day-notes`.
class DayNotesApi {
  const DayNotesApi(this._c);

  final ApiClient _c;

  Future<List<DayNote>> range(String from, String to) async {
    final r = await _c.get('/api/day-notes?from=$from&to=$to');
    return [
      for (final j in (r as List)) DayNote.fromJson((j as Map).cast<String, dynamic>()),
    ];
  }

  Future<void> add(String day, String text) =>
      _c.post('/api/day-notes', {'day': day, 'text': text});

  Future<void> remove(String id) =>
      _c.delete('/api/day-notes/${Uri.encodeComponent(id)}');
}

final dayNotesApiProvider =
    Provider<DayNotesApi>((ref) => DayNotesApi(ref.watch(apiClientProvider)));
