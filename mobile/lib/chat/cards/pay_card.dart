import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../api/api_client.dart';
import '../../theme/tokens.dart';
import 'approval_cards.dart';
import 'card_base.dart';

const _parts = ['number', 'exp', 'name', 'cvc'];
const _labels = {
  'number': 'Card number',
  'exp': 'Expiry (MM/YY)',
  'name': 'Name on card',
  'cvc': 'Security code (CVC)',
};
const _hints = {
  'number': AutofillHints.creditCardNumber,
  'exp': AutofillHints.creditCardExpirationDate,
  'name': AutofillHints.creditCardName,
  'cvc': AutofillHints.creditCardSecurityCode,
};
const _max = {'number': 23, 'exp': 7, 'name': 80, 'cvc': 4};
const _newCard = 'new';
const payNote = 'Roost types your card into the page; the bot never sees it.';
const payNoFields =
    'The page asks for no card details here. Pay clicks the button.';
const payFieldsFailed =
    "Couldn't read the payment page. You can still pay or take control.";

List<Object?> _list(Object? v) => v is List ? v : const [];

/// A saved card as the Pay card and Vault: cards show it: "Visa ending 4242".
String savedCardLabel(Json c) {
  final brand = str(c['brand']);
  final head = brand.isEmpty
      ? 'Card'
      : brand[0].toUpperCase() + brand.substring(1);
  return '$head ending ${str(c['last4'])}';
}

Future<Json> payCard(ApiClient api, String id, Json body) async =>
    ((await api.post('/api/approvals/$id/pay', body)) as Map)
        .cast<String, dynamic>();

/// The Pay card (owner, 2026-11-05; roost/payments/): the bot reached Pay. Fields only for the card parts the page
/// asks for; a saved card asks only the security code, every time. Pay sends the card in the request body only and
/// Roost types it into the page, then clicks the same Pay button; Don't pay answers no.
class PayCard extends StatefulWidget {
  const PayCard({super.key, required this.ctx, required this.card});
  final CardCtx<Json> ctx;
  final Json card;

  @override
  State<PayCard> createState() => _PayCardState();
}

class _PayCardState extends State<PayCard> {
  final _boxes = {for (final p in _parts) p: TextEditingController()};
  Json? _fields;
  bool _failed = false;
  String _picked = _newCard;
  bool _save = false;

  String get _id => str(widget.card['id']);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final got = (await widget.ctx.api.get('/api/approvals/$_id/pay') as Map)
          .cast<String, dynamic>();
      if (mounted) setState(() => _fields = got);
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  void dispose() {
    for (final box in _boxes.values) {
      box.clear();
      box.dispose();
    }
    super.dispose();
  }

  List<Json> get _saved => jsonList(_fields?['cards']);
  bool get _usingSaved =>
      _picked != _newCard && _saved.any((c) => str(c['id']) == _picked);
  List<String> get _asked {
    final parts = [for (final p in _list(_fields?['parts'])) '$p'];
    return [
      for (final p in _parts)
        if (parts.contains(p) && (!_usingSaved || p == 'cvc')) p,
    ];
  }

  Json _body() {
    if (_usingSaved) return {'card_id': _picked, 'cvc': _boxes['cvc']!.text};
    return {for (final p in _asked) p: _boxes[p]!.text, 'save': _save};
  }

  Future<void> _pay() async {
    final body = _body();
    await widget.ctx.act((api) => payCard(api, _id, body));
    // The security code is typed again every time.
    if (mounted) {
      _boxes['cvc']!.clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    final ctx = widget.ctx;
    final busy = ctx.busy;
    final fields = _fields;
    final refusal = str(fields?['refusal']);
    return CardFrame(
      title: 'Ready to pay',
      footer: [
        CardButton(
          'Pay',
          primary: true,
          onPressed: busy || (fields == null && !_failed) ? null : _pay,
        ),
        CardButton(
          "Don't pay",
          onPressed: busy
              ? null
              : () => ctx.act((api) => answerApproval(api, _id, 'no')),
        ),
      ],
      children: [
        for (final (i, s) in jsonList(widget.card['steps']).indexed)
          StepView(cardId: _id, index: i, step: s),
        if (fields == null && !_failed)
          const _Note('Reading the payment page…'),
        if (_failed) const _Note(payFieldsFailed),
        if (refusal.isNotEmpty) _Note(refusal),
        if (fields != null && refusal.isEmpty && _list(fields['parts']).isEmpty)
          const _Note(payNoFields),
        if (_saved.isNotEmpty && _list(fields?['parts']).isNotEmpty)
          RadioGroup<String>(
            groupValue: _picked,
            onChanged: (v) {
              if (!busy) setState(() => _picked = v ?? _newCard);
            },
            child: Column(
              children: [
                for (final c in _saved)
                  RadioListTile<String>(
                    dense: true,
                    enabled: !busy,
                    contentPadding: EdgeInsets.zero,
                    value: str(c['id']),
                    title: Text(savedCardLabel(c)),
                  ),
                RadioListTile<String>(
                  dense: true,
                  enabled: !busy,
                  contentPadding: EdgeInsets.zero,
                  value: _newCard,
                  title: const Text('Another card'),
                ),
              ],
            ),
          ),
        if (_asked.isNotEmpty)
          AutofillGroup(
            child: Column(
              children: [
                for (final p in _asked) _box(p, busy),
                if (!_usingSaved)
                  CheckboxListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    controlAffinity: ListTileControlAffinity.leading,
                    value: _save,
                    title: const Text(
                      'Save this card in Vault: cards (never the security code)',
                    ),
                    onChanged: busy
                        ? null
                        : (v) => setState(() => _save = v ?? false),
                  ),
              ],
            ),
          ),
        const _Note(payNote),
        if (ctx.error != null) CardError(ctx.error!),
      ],
    );
  }

  Widget _box(String part, bool busy) => Padding(
    padding: const EdgeInsets.only(top: Tokens.space2),
    child: TextField(
      key: Key('pay-$part'),
      controller: _boxes[part],
      enabled: !busy,
      obscureText: part == 'cvc',
      autocorrect: false,
      enableSuggestions: false,
      autofillHints: [_hints[part]!],
      keyboardType: part == 'name' ? TextInputType.name : TextInputType.number,
      inputFormatters: [LengthLimitingTextInputFormatter(_max[part])],
      decoration: InputDecoration(labelText: _labels[part], isDense: true),
    ),
  );
}

class _Note extends StatelessWidget {
  const _Note(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: Tokens.space1),
    child: Text(
      text,
      style: const TextStyle(
        color: Tokens.textSecondary,
        fontSize: Tokens.fsLabel,
      ),
    ),
  );
}
