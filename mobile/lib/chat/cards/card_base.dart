import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/api_error.dart';
import '../../api/providers.dart';
import '../../live/bot_frames.dart';
import '../../live/live_connection.dart';
import '../../theme/tokens.dart';
import '../web_mark.dart';

typedef Json = Map<String, dynamic>;

/// A message body that is a JSON object, or null for anything else.
Json? decodeBody(String body) {
  try {
    final v = jsonDecode(body);
    return v is Map ? v.cast<String, dynamic>() : null;
  } catch (_) {
    return null;
  }
}

String str(Object? v, [String fallback = '']) => v is String ? v : fallback;

List<Json> jsonList(Object? v) => v is List
    ? [
        for (final e in v)
          if (e is Map) e.cast<String, dynamic>()
      ]
    : const [];

const alreadyAnswered = 'Already answered.';

/// The badge words a card passes for web-made text; drawn as the quiet [WebMark].
const fromWebBadge = 'from web content';

/// The calm box every card sits in.
class CardFrame extends StatelessWidget {
  const CardFrame({
    super.key,
    required this.title,
    required this.children,
    this.footer = const [],
    this.badges = const [],
    this.calm = false,
  });

  /// A calm card (a Sign-in card is waiting for you, not stuck).
  final bool calm;
  final String title;
  final List<Widget> children;
  final List<Widget> footer;
  final List<String> badges;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: title,
      container: true,
      child: Container(
        margin: const EdgeInsets.symmetric(
            horizontal: Tokens.space3, vertical: Tokens.space2),
        padding: const EdgeInsets.all(Tokens.space3),
        decoration: BoxDecoration(
          color: Tokens.panel,
          border: Border.all(color: calm ? Tokens.info : Tokens.border),
          borderRadius: BorderRadius.circular(Tokens.radiusMd),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontSize: Tokens.fsBody, fontWeight: FontWeight.w600)),
            for (final b in badges)
              if (b == fromWebBadge)
                const WebMark()
              else
              Padding(
                padding: const EdgeInsets.only(top: Tokens.space1),
                child: Text(b,
                    style: const TextStyle(
                        color: Tokens.danger, fontSize: Tokens.fsCaption)),
              ),
            const SizedBox(height: Tokens.space2),
            ...children,
            if (footer.isNotEmpty) ...[
              const SizedBox(height: Tokens.space2),
              Wrap(
                  spacing: Tokens.space2,
                  runSpacing: Tokens.space2,
                  children: footer),
            ],
          ],
        ),
      ),
    );
  }
}

/// One quiet centred line (a card that has been answered, an activity).
class QuietLine extends StatelessWidget {
  const QuietLine(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(
            vertical: Tokens.space2, horizontal: Tokens.space6),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Flexible(
              child: Text(text,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
            ),
            ?trailing,
          ],
        ),
      );
}

class CardButton extends StatelessWidget {
  const CardButton(this.label,
      {super.key, required this.onPressed, this.primary = false});
  final String label;
  final VoidCallback? onPressed;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    const size = WidgetStatePropertyAll(Size(0, 40));
    return primary
        ? FilledButton(
            style: const ButtonStyle(minimumSize: size),
            onPressed: onPressed,
            child: Text(label))
        : OutlinedButton(
            style: const ButtonStyle(minimumSize: size),
            onPressed: onPressed,
            child: Text(label));
  }
}

class CardError extends StatelessWidget {
  const CardError(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: Tokens.space1),
        child: Text(text,
            style: const TextStyle(
                color: Tokens.dangerText, fontSize: Tokens.fsLabel)),
      );
}

/// What a card's builder gets: its current copy, whether a press is in
/// flight, the last error, and `act`, which runs one call and swaps in the
/// copy it returns. A 409 means someone else answered: the card reloads.
class CardCtx<T> {
  const CardCtx({
    required this.item,
    required this.busy,
    required this.error,
    required this.act,
    required this.api,
  });

  final T item;
  final bool busy;
  final String? error;
  final Future<void> Function(Future<T> Function(ApiClient api) call) act;
  final ApiClient api;
}

/// Loads one card's state, keeps it current on the live frames named in
/// [refreshOn], and hands the builder a [CardCtx]. [fetch] returns null for a
/// card that is gone ([gone] then draws it).
class FetchCard<T> extends ConsumerStatefulWidget {
  const FetchCard({
    super.key,
    required this.fetch,
    required this.builder,
    required this.gone,
    this.refreshOn = const {},
  });

  final Future<T?> Function(ApiClient api) fetch;
  final Widget Function(BuildContext context, CardCtx<T> ctx) builder;
  final Widget Function() gone;
  final Set<String> refreshOn;

  @override
  ConsumerState<FetchCard<T>> createState() => _FetchCardState<T>();
}

class _FetchCardState<T> extends ConsumerState<FetchCard<T>> {
  T? _item;
  bool _loaded = false;
  bool _busy = false;
  String? _error;
  int _ticket = 0;
  StreamSubscription<Frame>? _sub;

  @override
  void initState() {
    super.initState();
    _load();
    if (widget.refreshOn.isNotEmpty) {
      _sub = ref.read(frameBusProvider).stream.listen((f) {
        if (widget.refreshOn.contains(f['type'])) _load();
      });
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final ticket = ++_ticket;
    try {
      final found = await widget.fetch(ref.read(apiClientProvider));
      if (!mounted || ticket != _ticket) return;
      setState(() {
        _item = found;
        _loaded = true;
      });
    } on ApiException catch (e) {
      if (!mounted || ticket != _ticket) return;
      setState(() {
        _loaded = true;
        if (e.status == 404) {
          _item = null;
        } else {
          _error = e.message;
        }
      });
    }
  }

  Future<void> _act(Future<T> Function(ApiClient api) call) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final next = await call(ref.read(apiClientProvider));
      if (!mounted) return;
      setState(() => _item = next);
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.status == 409) {
        setState(() => _error = alreadyAnswered);
        _load();
      } else {
        setState(() => _error = e.message);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final item = _item;
    if (!_loaded) return const SizedBox(height: Tokens.space6);
    if (item == null) {
      return _error == null ? widget.gone() : CardError(_error!);
    }
    return widget.builder(
      context,
      CardCtx<T>(
        item: item,
        busy: _busy,
        error: _error,
        act: _act,
        api: ref.read(apiClientProvider),
      ),
    );
  }
}
