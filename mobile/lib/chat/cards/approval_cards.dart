import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/api_error.dart';
import '../../api/providers.dart';
import '../../theme/tokens.dart';
import 'approval_answers.dart';
import 'card_base.dart';
import 'choice_card.dart';
import 'pay_card.dart';
import 'send_card.dart';

const _fromWeb = fromWebBadge;
const _actTools = {'click', 'type', 'press_key'};

/// An "approval" message: the live card by its id (Ask, Proposal or options).
/// A card this app cannot load shows the question's words and no buttons.
class ApprovalMessageCard extends StatelessWidget {
  const ApprovalMessageCard({super.key, required this.body, this.answer});
  final String body;

  /// The answer line that followed this card in the chat, if any.
  final String? answer;

  @override
  Widget build(BuildContext context) {
    final ref = parseApprovalMessage(body);
    if (ref == null) return const SizedBox.shrink();
    return FetchCard<Json>(
      key: ValueKey(ref.cardId),
      refreshOn: const {'approval_card'},
      fetch: (api) async => (await api.get('/api/approvals/${ref.cardId}')
              as Map)
          .cast<String, dynamic>(),
      gone: () => QuietLine(ref.steps.join(' · ')),
      builder: (context, ctx) {
        final card = ctx.item;
        if (card['choice'] is Map) {
          return ChoiceCard(ctx: ctx, card: card, answer: answer);
        }
        if (card['state'] != 'open') return QuietLine(closedLine(card));
        if (card['kind'] == 'plan') return PlanCard(ctx: ctx, card: card);
        if (card['pay'] == true) return PayCard(ctx: ctx, card: card);
        return card['send'] == true
            ? SendCard(ctx: ctx, card: card)
            : AskCard(ctx: ctx, card: card);
      },
    );
  }
}

Future<Json> answerApproval(ApiClient api, String id, String answer,
    [Json extra = const {}]) async {
  final r = await api.post(
      '/api/approvals/$id/answer', {'answer': answer, ...extra}) as Map;
  return r.cast<String, dynamic>();
}

/// An Open card (roost/talk/new_site.py): the bot wants a site you didn't name; its button says Open.
bool _opensSite(Json card) {
  final steps = jsonList(card['steps']);
  if (steps.length != 1) return false;
  final step = steps.first;
  return step['tool'] == 'open_page' && step['floor'] == 'new_site';
}

class AskCard extends StatelessWidget {
  const AskCard({super.key, required this.ctx, required this.card});
  final CardCtx<Json> ctx;
  final Json card;

  @override
  Widget build(BuildContext context) {
    final id = str(card['id']);
    void send(String a) => ctx.act((api) => answerApproval(api, id, a));
    return CardFrame(
      title: 'Needs your OK',
      badges: [if ((card['from_web'] ?? card['tainted']) == true) _fromWeb],
      footer: [
        CardButton(_opensSite(card) ? 'Open' : 'Yes',
            primary: true, onPressed: ctx.busy ? null : () => send('yes')),
        if (card['session_offer'] == true)
          CardButton('Yes for this session',
              onPressed: ctx.busy ? null : () => send('yes_session')),
        CardButton('No', onPressed: ctx.busy ? null : () => send('no')),
      ],
      children: [
        for (final (i, s) in jsonList(card['steps']).indexed)
          StepView(cardId: id, index: i, step: s),
        if (ctx.error != null) CardError(ctx.error!),
      ],
    );
  }
}

class PlanCard extends StatelessWidget {
  const PlanCard({super.key, required this.ctx, required this.card});
  final CardCtx<Json> ctx;
  final Json card;

  Future<void> _edit(BuildContext context, String id) async {
    final words = await askForText(context,
        title: 'What should change?', max: 2000, action: 'Send');
    if (words != null && words.trim().isNotEmpty) {
      ctx.act((api) => answerApproval(api, id, 'edit', {'text': words.trim()}));
    }
  }

  @override
  Widget build(BuildContext context) {
    final id = str(card['id']);
    return CardFrame(
      title: 'Proposal',
      badges: [if (card['tainted'] == true) _fromWeb],
      footer: [
        CardButton('Accept',
            primary: true,
            onPressed: ctx.busy
                ? null
                : () => ctx.act((api) => answerApproval(api, id, 'accept'))),
        CardButton('Edit',
            onPressed: ctx.busy ? null : () => _edit(context, id)),
        CardButton('Decline',
            onPressed: ctx.busy
                ? null
                : () => ctx.act((api) => answerApproval(api, id, 'decline'))),
      ],
      children: [
        for (final (i, s) in jsonList(card['steps']).indexed)
          StepView(cardId: id, index: i, step: s, number: i + 1),
        if (ctx.error != null) CardError(ctx.error!),
      ],
    );
  }
}

/// A small text sheet: returns the words, or null when closed.
Future<String?> askForText(BuildContext context,
    {required String title,
    required int max,
    required String action,
    String initial = ''}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) =>
        _TextSheet(title: title, max: max, action: action, initial: initial),
  );
}

/// The sheet owns its text controller, so it is disposed only after the
/// sheet's closing animation no longer draws the field.
class _TextSheet extends StatefulWidget {
  const _TextSheet(
      {required this.title,
      required this.max,
      required this.action,
      required this.initial});
  final String title;
  final int max;
  final String action;
  final String initial;

  @override
  State<_TextSheet> createState() => _TextSheetState();
}

class _TextSheetState extends State<_TextSheet> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(Tokens.space4, Tokens.space4, Tokens.space4,
          MediaQuery.of(context).viewInsets.bottom + Tokens.space4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.title, style: const TextStyle(fontSize: Tokens.fsLead)),
          const SizedBox(height: Tokens.space2),
          TextField(
            controller: _controller,
            maxLength: widget.max,
            maxLines: 8,
            minLines: 3,
            autofocus: true,
          ),
          Align(
            alignment: Alignment.centerRight,
            child: CardButton(widget.action,
                primary: true,
                onPressed: () => Navigator.pop(context, _controller.text)),
          ),
        ],
      ),
    );
  }
}

/// One step: what it will do, the hard-floor badge, the button's picture for
/// a screen act, the outside-content line, its rows and diff.
class StepView extends ConsumerWidget {
  const StepView(
      {super.key,
      required this.cardId,
      required this.index,
      required this.step,
      this.number});
  final String cardId;
  final int index;
  final Json step;
  final int? number;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final diff = step['diff'] is Map ? (step['diff'] as Map) : null;
    return Padding(
      padding: const EdgeInsets.only(bottom: Tokens.space2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${number != null ? '$number. ' : ''}${str(step['title'])}'
              '${step['floor'] != null ? '  · Hard floor' : ''}'),
          if (_actTools.contains(step['tool']))
            CropImage(cardId: cardId, index: index),
          for (final r in jsonList(step['rows']))
            if (str(r['key']).startsWith(draftRowKey))
              DraftRow(label: str(r['label']), text: str(r['value']))
            else
              Text('${str(r['label'])}: ${str(r['value'])}',
                  style: const TextStyle(
                      color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          if (str(step['detail']).isNotEmpty)
            Text(str(step['detail']),
                style: const TextStyle(
                    color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          if (step['tainted_basis'] == true)
            const Text('Based on outside content',
                style: TextStyle(
                    color: Tokens.danger, fontSize: Tokens.fsCaption)),
          if (diff != null && str(diff['text']).isNotEmpty)
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text('Changes +${diff['plus']} −${diff['minus']}',
                  style: const TextStyle(fontSize: Tokens.fsLabel)),
              children: [
                SelectableText(str(diff['text']),
                    style: const TextStyle(
                        fontFamily: 'monospace', fontSize: Tokens.fsCaption)),
              ],
            ),
        ],
      ),
    );
  }
}

/// The picture of the button a screen act will press: fetched once from the
/// full card (live frames and lists never carry it).
class CropImage extends ConsumerStatefulWidget {
  const CropImage({super.key, required this.cardId, required this.index});
  final String cardId;
  final int index;

  @override
  ConsumerState<CropImage> createState() => _CropImageState();
}

class _CropImageState extends ConsumerState<CropImage> {
  static final _base64 = RegExp(r'^[A-Za-z0-9+/]+={0,2}$');
  Widget _shown = const SizedBox.shrink();

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    try {
      final card = await ref
          .read(apiClientProvider)
          .get('/api/approvals/${widget.cardId}?full=1') as Map;
      final steps = card['steps'] as List? ?? const [];
      final crop = widget.index < steps.length
          ? (steps[widget.index] as Map)['crop']
          : null;
      if (!mounted || crop is! String || !_base64.hasMatch(crop)) return;
      setState(() => _shown = Padding(
            padding: const EdgeInsets.symmetric(vertical: Tokens.space1),
            child: Image.memory(base64Decode(crop),
                semanticLabel: 'The button', gaplessPlayback: true),
          ));
    } on ApiException {
      if (!mounted) return;
      setState(() => _shown = const Text(
          "Couldn't load the picture of the button.",
          style:
              TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)));
    }
  }

  @override
  Widget build(BuildContext context) => _shown;
}
