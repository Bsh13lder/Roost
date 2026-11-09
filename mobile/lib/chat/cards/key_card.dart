import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../theme/tokens.dart';
import 'card_base.dart';

/// The Add a key card a bot raises with `request_connector`: the service, its
/// site and the bot's reason, and a write-only key field. The key is sent
/// once, cleared from the field the moment Save is pressed, and is never
/// shown, logged or kept in app state.
class KeyRequestCard extends StatelessWidget {
  const KeyRequestCard({super.key, required this.body});
  final String body;

  @override
  Widget build(BuildContext context) {
    final id = str(decodeBody(body)?['request_id']);
    if (id.isEmpty) return QuietLine(body);
    return FetchCard<Json>(
      key: ValueKey(id),
      refreshOn: const {'connectors_changed'},
      fetch: (api) async =>
          ((await api.get('/api/connector-requests/$id')) as Map)
              .cast<String, dynamic>(),
      gone: () => const QuietLine('This card is gone.'),
      builder: (context, ctx) {
        final r = ctx.item;
        if (r['state'] != 'open') {
          return QuietLine(r['state'] == 'saved'
              ? 'Key added · ${str(r['service'])}'
              : 'Not now');
        }
        return _KeyForm(requestId: id, request: r, ctx: ctx);
      },
    );
  }
}

class _KeyForm extends StatefulWidget {
  const _KeyForm(
      {required this.requestId, required this.request, required this.ctx});
  final String requestId;
  final Json request;
  final CardCtx<Json> ctx;

  @override
  State<_KeyForm> createState() => _KeyFormState();
}

class _KeyFormState extends State<_KeyForm> {
  final _key = TextEditingController();
  bool _sent = false;

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  Future<Json> _call(ApiClient api, String tail, [Json? body]) async =>
      ((await api.post('/api/connector-requests/${widget.requestId}/$tail',
          body)) as Map)
          .cast<String, dynamic>();

  void _save() {
    final secret = _key.text;
    if (secret.isEmpty) return;
    // Gone from the field before the call starts.
    _key.clear();
    setState(() => _sent = true);
    widget.ctx.act((api) => _call(api, 'save', {'secret': secret}));
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.request;
    final busy = widget.ctx.busy;
    return CardFrame(
      title: 'Add a key',
      badges: [if (r['tainted'] == true) 'from web content'],
      footer: [
        CardButton('Save', primary: true, onPressed: busy ? null : _save),
        CardButton('Not now',
            onPressed: busy
                ? null
                : () => widget.ctx.act((api) => _call(api, 'decline'))),
      ],
      children: [
        Text(str(r['service']),
            style: const TextStyle(fontWeight: FontWeight.w600)),
        Text(str(r['host']),
            style: const TextStyle(
                color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
        Text(str(r['why']),
            style: const TextStyle(color: Tokens.textSecondary)),
        const SizedBox(height: Tokens.space2),
        TextField(
          key: const Key('key-field'),
          controller: _key,
          obscureText: true,
          enableSuggestions: false,
          autocorrect: false,
          enableIMEPersonalizedLearning: false,
          autofillHints: null,
          maxLength: 500,
          decoration: const InputDecoration(
              labelText: 'Key (kept private, never shown again)',
              counterText: ''),
        ),
        if (widget.ctx.error != null)
          CardError(_sent
              ? '${widget.ctx.error!} Type the key again to retry.'
              : widget.ctx.error!),
      ],
    );
  }
}
