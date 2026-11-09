import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'approval_cards.dart';
import 'card_base.dart';

/// A Send card's text rows (roost/approvals/rows.py DRAFT_ROW_KEY): shown whole.
const draftRowKey = 'draft';
const _draftMaxHeight = 240.0;
const _changeMaxChars =
    4000; // the server's limit on an edit (APPROVAL_EDIT_TEXT_MAX)

/// The Send card (owner, 2026-11-03; roost/approvals/send_card.py): the bot filled the form with its own text. Every
/// box it typed shows whole, and Send · Don't send · Change it… answer it; Change it… sends what it should say instead.
class SendCard extends StatelessWidget {
  const SendCard({super.key, required this.ctx, required this.card});
  final CardCtx<Json> ctx;
  final Json card;

  Future<void> _change(BuildContext context, String id) async {
    final words = await askForText(
      context,
      title: 'What should it say instead?',
      max: _changeMaxChars,
      action: 'Send change',
    );
    if (words != null && words.trim().isNotEmpty) {
      ctx.act((api) => answerApproval(api, id, 'edit', {'text': words.trim()}));
    }
  }

  @override
  Widget build(BuildContext context) {
    final id = str(card['id']);
    void send(String a) => ctx.act((api) => answerApproval(api, id, a));
    return CardFrame(
      title: 'Ready to send',
      badges: [if (card['from_web'] == true) fromWebBadge],
      footer: [
        CardButton(
          'Send',
          primary: true,
          onPressed: ctx.busy ? null : () => send('yes'),
        ),
        CardButton("Don't send", onPressed: ctx.busy ? null : () => send('no')),
        CardButton(
          'Change it…',
          onPressed: ctx.busy ? null : () => _change(context, id),
        ),
      ],
      children: [
        for (final (i, s) in jsonList(card['steps']).indexed)
          StepView(cardId: id, index: i, step: s),
        if (ctx.error != null) CardError(ctx.error!),
      ],
    );
  }
}

/// One box's text on a Send card: its label, then the whole text, scrolling inside its box when long.
class DraftRow extends StatelessWidget {
  const DraftRow({super.key, required this.label, required this.text});
  final String label;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: Tokens.space1),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: Tokens.textSecondary,
              fontSize: Tokens.fsLabel,
            ),
          ),
          Container(
            width: double.infinity,
            constraints: const BoxConstraints(maxHeight: _draftMaxHeight),
            padding: const EdgeInsets.all(Tokens.space2),
            decoration: BoxDecoration(
              color: Tokens.raised,
              borderRadius: BorderRadius.circular(Tokens.radiusSm),
            ),
            child: SingleChildScrollView(
              child: SelectableText(
                text,
                style: const TextStyle(
                  color: Tokens.text,
                  fontSize: Tokens.fsBody,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
