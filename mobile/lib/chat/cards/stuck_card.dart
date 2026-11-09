import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_error.dart';
import '../../computer/computer_api.dart' show ComputerApi;
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'card_base.dart';
import 'secret_field.dart';

const _taintNote =
    'This link came from a web page the bot read. Check it before you open it.';
const _repliedLine = 'You answered in the chat';

/// A Stuck card message: the bot hit a block it can't clear alone. Take
/// control (opens the live computer screen), Try
/// again, Give up and Later. A Sign-in card says "Roost never sees your
/// password." and asks "Keep me signed in on this computer?" on Give it back.
/// Reply (owner, 2026-11-02) quotes the card for your next message, which
/// answers it: the card then reads "You answered in the chat".
class StuckMessageCard extends StatefulWidget {
  const StuckMessageCard(
      {super.key,
      required this.body,
      required this.tainted,
      this.botName,
      this.onReply});
  final String body;
  final bool tainted;
  final String? botName;

  /// Quote this card in the composer; null where you can't write.
  final VoidCallback? onReply;

  @override
  State<StuckMessageCard> createState() => _StuckMessageCardState();
}

class _StuckMessageCardState extends State<StuckMessageCard> {
  bool _holding = false;

  @override
  Widget build(BuildContext context) {
    final data = decodeBody(widget.body);
    final cardId = str(data?['card_id']);
    if (data == null || cardId.isEmpty) return QuietLine(widget.body);
    return FetchCard<Json>(
      key: ValueKey(cardId),
      refreshOn: const {'stuck_card'},
      fetch: (api) async {
        try {
          return ((await api.get('/api/stuck/$cardId')) as Map)
              .cast<String, dynamic>();
        } on ApiException catch (e) {
          if (e.status == 404) return null;
          rethrow;
        }
      },
      gone: () => QuietLine(str(data['line'], 'Cleared')),
      builder: (context, ctx) => _build(context, ctx, data, cardId),
    );
  }

  Widget _build(
      BuildContext context, CardCtx<Json> ctx, Json data, String cardId) {
    final card = ctx.item;
    final host = str(data['host']);
    final url = str(data['url']);
    final signIn = data['sign_in'] == true || card['sign_in'] == true;
    final state = str(card['state'], 'open');
    if (state == 'replied') return const QuietLine(_repliedLine);
    if (state != 'open') {
      final word = switch (state) {
        'cleared' => 'Cleared',
        'given_up' => 'Stopped',
        _ => 'Blocked',
      };
      return QuietLine(host.isEmpty ? word : '$word: $host');
    }
    Future<void> post(String tail, [Json? body]) => ctx.act((api) async =>
        ((await api.post('/api/stuck/$cardId/$tail', body)) as Map)
            .cast<String, dynamic>());
    final busy = ctx.busy;
    return CardFrame(
      calm: signIn,
      title: _title(host, url, signIn),
      badges: [if (widget.tainted && url.isNotEmpty) _taintNote],
      footer: [
        ..._buttons(context, ctx, data, post, signIn, busy),
        if (widget.onReply != null)
          CardButton('Reply', onPressed: busy ? null : widget.onReply),
      ],
      children: [
        Text(str(data['line']),
            style: const TextStyle(color: Tokens.textSecondary)),
        if (url.isNotEmpty)
          Text(signIn ? host : url,
              style: const TextStyle(
                  color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
        if (signIn && !_holding && _secretKind(card) != null)
          SecretField(
              host: host,
              kind: _secretKind(card)!,
              botName: widget.botName ?? 'the bot',
              busy: busy,
              onSend: (value, save) => post(
                  'secret', {'value': value, 'save': ?save})),
        if (signIn)
          const Text('Roost never sees your password.',
              style:
                  TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
        if (_holding)
          Text(
              "You have control. Clear it in ${widget.botName ?? 'the bot'}'s window, then give it back.",
              style: TextStyle(color: AccentColors.of(context).strong)),
        if (ctx.error != null) CardError(ctx.error!),
      ],
    );
  }

  /// "password" or "code" when the bot asked you for one on this card.
  String? _secretKind(Json card) => switch (card['secret_field']) {
        'password' => 'password',
        'code' => 'code',
        _ => null,
      };

  String _title(String host, String url, bool signIn) {
    if (host.isEmpty || url.isEmpty) return 'Needs your help';
    return signIn ? 'Waiting for you to sign in on $host' : 'Stuck on $host';
  }

  List<Widget> _buttons(BuildContext context, CardCtx<Json> ctx, Json data,
      Future<void> Function(String, [Json?]) post, bool signIn, bool busy) {
    final botId = str(data['bot_id']);
    final cardId = str(data['card_id']);
    // A Sign-in card's Take control is the server's open-sign-in: the card's
    // page on the bot's computer, then you hold control.
    Future<void> control() async {
      await ctx.act((api) async {
        if (signIn) {
          await api.post('/api/stuck/$cardId/open-sign-in');
        } else {
          await api.post('/api/bots/$botId/control');
        }
        return ctx.item;
      });
      if (!context.mounted) return;
      setState(() => _holding = true);
      await context.push('/computer/$botId?go=control');
      if (mounted) await _syncHolding(botId, ctx);
    }

    if (_holding) {
      return [
        CardButton('See its screen',
            onPressed: () async {
              await context.push('/computer/$botId?go=control');
              if (mounted) await _syncHolding(botId, ctx);
            }),
        CardButton('Give it back',
            primary: true,
            onPressed: busy
                ? null
                : () async {
                    final keep = signIn ? await _askKeep(context) : null;
                    if (signIn && keep == null) return;
                    await post('clear', keep == null ? null : {'keep': keep});
                  }),
      ];
    }
    if (signIn) {
      return [
        CardButton('Take control', primary: true, onPressed: busy ? null : control),
        CardButton('Later', onPressed: busy ? null : () => post('later')),
        CardButton('Check again',
            onPressed: busy ? null : () => post('clear', {'how': 'try_again'})),
      ];
    }
    return [
      CardButton('Take control', primary: true, onPressed: busy ? null : control),
      CardButton('Try again', onPressed: busy ? null : () => post('clear')),
      CardButton('Give up', onPressed: busy ? null : () => post('give-up')),
      CardButton('Later', onPressed: busy ? null : () => post('later')),
    ];
  }

  /// After the Computer screen closes: still holding control or not.
  Future<void> _syncHolding(String botId, CardCtx<Json> ctx) async {
    try {
      final held = await ComputerApi(ctx.api).held(botId);
      if (mounted) setState(() => _holding = held);
    } catch (_) {
      // The card keeps its last state; the next refresh corrects it.
    }
  }

  Future<bool?> _askKeep(BuildContext context) => showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Keep me signed in on this computer?'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Just this time')),
            TextButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Keep me signed in')),
          ],
        ),
      );
}
