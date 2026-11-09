import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'approval_answers.dart';
import 'approval_cards.dart';
import 'card_base.dart';

const _ownMax = 1000;

/// An options card (`ask_choice`): the question, 2 to 4 options with the safe
/// one marked, your own words when allowed, and Dismiss, which counts as No.
/// Once answered it shrinks to one line with your answer.
class ChoiceCard extends StatefulWidget {
  const ChoiceCard(
      {super.key, required this.ctx, required this.card, this.answer});
  final CardCtx<Json> ctx;
  final Json card;
  final String? answer;

  @override
  State<ChoiceCard> createState() => _ChoiceCardState();
}

class _ChoiceCardState extends State<ChoiceCard> {
  final _own = TextEditingController();
  String? _said;
  bool _showOptions = false;

  @override
  void dispose() {
    _own.dispose();
    super.dispose();
  }

  Json get _choice => (widget.card['choice'] as Map).cast<String, dynamic>();
  List<String> get _options =>
      [for (final o in (_choice['options'] as List? ?? const [])) str(o)];

  void _send(String answer, Json extra, String said) {
    setState(() => _said = said);
    widget.ctx.act((api) =>
        answerApproval(api, str(widget.card['id']), answer, extra));
  }

  @override
  Widget build(BuildContext context) {
    final card = widget.card;
    final words = widget.answer ?? _said;
    if (card['state'] == 'approved' && words != null) return _done(words);
    if (card['state'] != 'open') return QuietLine(closedLine(card));
    final busy = widget.ctx.busy;
    final safe = (_choice['safe'] as num?)?.toInt() ?? -1;
    return CardFrame(
      title: 'Needs your choice',
      badges: [if (card['tainted'] == true) 'from web content'],
      children: [
        Text(str(_choice['question']),
            style: const TextStyle(fontSize: Tokens.fsLead)),
        const SizedBox(height: Tokens.space2),
        Wrap(spacing: Tokens.space2, runSpacing: Tokens.space2, children: [
          for (final (i, option) in _options.indexed)
            CardButton(i == safe ? '$option · Safe choice' : option,
                primary: i == safe,
                onPressed: busy
                    ? null
                    : () => _send('pick', {'choice': i}, option)),
        ]),
        if (_choice['own'] == true) _ownField(busy),
        Row(children: [
          Expanded(
            child: Text(str(_choice['why']),
                style: const TextStyle(
                    color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
          ),
          TextButton(
              onPressed: busy ? null : () => _send('no', const {}, 'Dismissed'),
              child: const Text('Dismiss')),
        ]),
        if (widget.ctx.error != null) CardError(widget.ctx.error!),
      ],
    );
  }

  Widget _ownField(bool busy) => Padding(
        padding: const EdgeInsets.only(top: Tokens.space2),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _own,
              maxLength: _ownMax,
              enabled: !busy,
              decoration: const InputDecoration(
                  hintText: 'Type your own', counterText: ''),
            ),
          ),
          const SizedBox(width: Tokens.space2),
          CardButton('Send', onPressed: busy ? null : _sendOwn),
        ]),
      );

  void _sendOwn() {
    final text = _own.text.trim();
    if (text.isEmpty) return;
    _send('own', {'text': text}, text);
  }

  Widget _done(String answer) {
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: Tokens.space4, vertical: Tokens.space2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _showOptions = !_showOptions),
            child: Text('✓ You answered: $answer',
                key: const Key('choice-done'),
                style: const TextStyle(
                    color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          ),
          if (_showOptions) ...[
            Text(str(_choice['question']),
                style: const TextStyle(
                    color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            for (final o in _options)
              Text('• $o${o == answer ? ' (your answer)' : ''}',
                  style: const TextStyle(
                      color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
          ],
        ],
      ),
    );
  }
}
