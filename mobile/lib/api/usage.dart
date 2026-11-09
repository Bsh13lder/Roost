import 'api_client.dart';

/// Token usage (docs/plans/2026-11-04-roost-token-usage.md):
/// `GET /api/usage?days=N` and `GET /api/bots/{id}/usage?days=N`.
/// Every field is optional on the wire: a missing number reads as 0 and a
/// missing list as empty, so an older gateway shows "No tokens used yet."

const usageWeekDays = 7;

int _int(Object? v) => v is num ? v.toInt() : 0;

Map<String, dynamic> _map(Object? v) =>
    v is Map ? v.cast<String, dynamic>() : const {};

List<UsageDay> _days(Object? v) => v is List
    ? [for (final d in v) if (d is Map) UsageDay.fromJson(d.cast())]
    : const [];

class UsageCounts {
  const UsageCounts({
    this.input = 0,
    this.output = 0,
    this.cacheRead = 0,
    this.cacheWrite = 0,
    this.calls = 0,
    this.tokensIn = 0,
    this.tokensOut = 0,
    this.tokens = 0,
  });

  factory UsageCounts.fromJson(Object? json) {
    final m = _map(json);
    return UsageCounts(
      input: _int(m['input']),
      output: _int(m['output']),
      cacheRead: _int(m['cache_read']),
      cacheWrite: _int(m['cache_write']),
      calls: _int(m['calls']),
      tokensIn: _int(m['tokens_in']),
      tokensOut: _int(m['tokens_out']),
      tokens: _int(m['tokens']),
    );
  }

  final int input, output, cacheRead, cacheWrite, calls;
  final int tokensIn, tokensOut, tokens;
}

class UsageDay {
  const UsageDay({required this.day, required this.counts});

  factory UsageDay.fromJson(Map<String, dynamic> m) => UsageDay(
      day: m['day'] is String ? m['day'] as String : '',
      counts: UsageCounts.fromJson(m));

  final String day;
  final UsageCounts counts;
}

class BusiestBot {
  const BusiestBot({required this.botId, required this.name});

  final String botId;
  final String name;
}

/// One bot's usage (also the shape of the whole-account totals).
class BotUsage {
  const BotUsage({
    required this.total,
    required this.todayTotal,
    required this.perDay,
  });

  factory BotUsage.fromJson(Object? json) {
    final m = _map(json);
    return BotUsage(
      total: UsageCounts.fromJson(m['total']),
      todayTotal: UsageCounts.fromJson(m['today_total']),
      perDay: _days(m['per_day']),
    );
  }

  final UsageCounts total;
  final UsageCounts todayTotal;
  final List<UsageDay> perDay;
}

class UsageSummary extends BotUsage {
  const UsageSummary({
    required super.total,
    required super.todayTotal,
    required super.perDay,
    this.busiest,
  });

  factory UsageSummary.fromJson(Object? json) {
    final m = _map(json);
    final base = BotUsage.fromJson(m);
    final b = _map(m['busiest']);
    final name = b['name'];
    return UsageSummary(
      total: base.total,
      todayTotal: base.todayTotal,
      perDay: base.perDay,
      busiest: name is String && name.isNotEmpty
          ? BusiestBot(botId: '${b['bot_id'] ?? ''}', name: name)
          : null,
    );
  }

  final BusiestBot? busiest;
}

String _oneDecimal(double v) {
  final s = v.toStringAsFixed(1);
  return s.endsWith('.0') ? s.substring(0, s.length - 2) : s;
}

/// 999 → "999", 12345 → "12.3k", 1234567 → "1.2M".
String compactTokens(int n) {
  if (n >= 1000000) return '${_oneDecimal(n / 1000000)}M';
  if (n >= 1000) return '${_oneDecimal(n / 1000)}k';
  return '$n';
}

/// Settings' one line: "Tokens today: N · this week: M · busiest: Scout".
String usageLine(UsageSummary s) {
  final head = 'Tokens today: ${compactTokens(s.todayTotal.tokens)} · '
      'this week: ${compactTokens(s.total.tokens)}';
  final busiest = s.busiest;
  return busiest == null ? head : '$head · busiest: ${busiest.name}';
}

Future<UsageSummary> fetchUsage(ApiClient api,
        {int days = usageWeekDays}) async =>
    UsageSummary.fromJson(await api.get('/api/usage?days=$days'));

Future<BotUsage> fetchBotUsage(ApiClient api, String botId,
        {int days = usageWeekDays}) async =>
    BotUsage.fromJson(await api
        .get('/api/bots/${Uri.encodeComponent(botId)}/usage?days=$days'));
