import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';

typedef Json = Map<String, dynamic>;

const authStyles = [
  ('bearer', 'Bearer token'),
  ('header', 'Header'),
  ('query', 'Query parameter'),
];

/// Opens the form; `connector` null adds one. True when saved.
Future<bool> showConnectorForm(BuildContext context,
    {String? botId, Json? connector}) async {
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (_) => ConnectorForm(botId: botId, connector: connector),
  );
  return saved == true;
}

/// Add or edit a connector. The key field is write-only: it is cleared the
/// moment Save is pressed, is never filled from the server (only a hint
/// like "key set ••••abcd" is shown), and is never logged or kept.
class ConnectorForm extends ConsumerStatefulWidget {
  const ConnectorForm({super.key, this.botId, this.connector});

  final String? botId;
  final Json? connector;

  @override
  ConsumerState<ConnectorForm> createState() => _ConnectorFormState();
}

class _ConnectorFormState extends ConsumerState<ConnectorForm> {
  late final _name = TextEditingController(text: _c('name'));
  late final _purpose = TextEditingController(text: _c('purpose'));
  late final _url = TextEditingController(text: _c('base_url'));
  late final _authName = TextEditingController(text: _c('auth_name'));
  late final _prefixes = TextEditingController(
      text: [for (final p in (widget.connector?['allowed_prefixes'] as List? ?? const [])) '$p']
          .join('\n'));
  final _key = TextEditingController();
  late String _style = _c('auth_style').isEmpty ? 'bearer' : _c('auth_style');
  late bool _everyBot = widget.connector == null
      ? widget.botId == null
      : widget.connector!['bot_ids'] == null;
  bool _busy = false;
  String? _error;

  String _c(String k) => widget.connector?[k] as String? ?? '';
  String? get _id => widget.connector?['id'] as String?;

  @override
  void dispose() {
    for (final c in [_name, _purpose, _url, _authName, _prefixes, _key]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final secret = _key.text;
    // Gone from the field before the call starts.
    _key.clear();
    final fields = <String, dynamic>{
      'name': _name.text.trim(),
      'purpose': _purpose.text.trim(),
      'base_url': _url.text.trim(),
      'auth_style': _style,
      'auth_name': _authName.text.trim(),
      'allowed_prefixes': [
        for (final l in _prefixes.text.split('\n'))
          if (l.trim().isNotEmpty) l.trim(),
      ],
      if (secret.isNotEmpty) 'secret': secret,
      if (_everyBot || widget.botId == null)
        'all_bots': true
      else
        'bot_ids': [widget.botId],
    };
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiClientProvider);
    try {
      if (_id == null) {
        fields.remove('all_bots');
        await api.post('/api/connectors', fields);
      } else {
        await api.patch('/api/connectors/${Uri.encodeComponent(_id!)}', fields);
      }
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() => _error = secret.isEmpty
            ? describe(e)
            : '${describe(e)} Type the key again to retry.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    if (!await confirm(context, 'Delete this connector for every bot?', 'Delete')) {
      return;
    }
    if (!mounted) return;
    final ok = await attempt(
        context,
        () => ref
            .read(apiClientProvider)
            .delete('/api/connectors/${Uri.encodeComponent(_id!)}'));
    if (ok && mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final hint = _c('key_hint');
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(Tokens.space4),
          children: [
            _field(_name, 'Name', max: 40),
            _field(_purpose, 'What it is for', max: 300),
            _field(_url, 'Address (https://…)', max: 300, url: true),
            DropdownButtonFormField<String>(
              initialValue: _style,
              decoration: const InputDecoration(labelText: 'How the key is sent'),
              items: [
                for (final (id, label) in authStyles)
                  DropdownMenuItem(value: id, child: Text(label)),
              ],
              onChanged: (v) => setState(() => _style = v ?? 'bearer'),
            ),
            _field(_authName,
                _style == 'query' ? 'Parameter name' : 'Header name', max: 64),
            TextField(
              key: const Key('connector-key'),
              controller: _key,
              obscureText: true,
              enableSuggestions: false,
              autocorrect: false,
              enableIMEPersonalizedLearning: false,
              maxLength: 4096,
              decoration: InputDecoration(
                labelText: 'Key',
                counterText: '',
                helperText: _id == null
                    ? 'Write-only: Roost never shows it again, and bots never see it.'
                    : '${hint.isEmpty ? 'Key set' : hint}. Leave empty to keep the saved key.',
              ),
            ),
            TextField(
              controller: _prefixes,
              minLines: 1,
              maxLines: 4,
              decoration: const InputDecoration(
                  labelText: 'Allowed paths',
                  helperText: 'Optional, one per line, such as /v3/site-explorer.'),
            ),
            if (widget.botId != null)
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Every bot'),
                subtitle: const Text('Off: only this bot'),
                value: _everyBot,
                onChanged: (v) => setState(() => _everyBot = v),
              ),
            if (_error != null) Quiet(_error!, bad: true),
            Row(children: [
              if (_id != null)
                TextButton(
                    onPressed: _delete,
                    child: const Text('Delete',
                        style: TextStyle(color: Tokens.dangerText))),
              const Spacer(),
              FilledButton(
                  key: const Key('connector-save'),
                  onPressed: _busy ? null : _save,
                  child: const Text('Save')),
            ]),
          ],
        ),
      ),
    );
  }

  Widget _field(TextEditingController c, String label,
          {int max = 100, bool url = false}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: Tokens.space2),
        child: TextField(
          controller: c,
          maxLength: max,
          keyboardType: url ? TextInputType.url : null,
          decoration: InputDecoration(labelText: label, counterText: ''),
        ),
      );
}
