import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/gateway_url.dart';
import '../../api/providers.dart';
import '../../theme/tokens.dart';

/// The gateway address. Saving a new one signs out; the sign-in screen then
/// opens with the new address filled in.
class GatewayField extends ConsumerStatefulWidget {
  const GatewayField({super.key});

  @override
  ConsumerState<GatewayField> createState() => _GatewayFieldState();
}

class _GatewayFieldState extends ConsumerState<GatewayField> {
  late final TextEditingController _url =
      TextEditingController(text: ref.read(authProvider).baseUrl);
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final check = checkGatewayUrl(_url.text);
    final url = check.url;
    if (url == null) {
      setState(() => _error = check.error);
      return;
    }
    if (url == ref.read(authProvider).baseUrl) {
      setState(() => _error = null);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    await ref.read(authProvider.notifier).changeGateway(url);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          key: const Key('settings-gateway'),
          controller: _url,
          keyboardType: TextInputType.url,
          autocorrect: false,
          enableSuggestions: false,
          onSubmitted: (_) => _save(),
          decoration: const InputDecoration(
            labelText: 'Gateway address',
            helperText: 'Saving a new address signs you out.',
            helperStyle: TextStyle(color: Tokens.textFaint),
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: Tokens.space2),
          Text(_error!,
              key: const Key('gateway-error'),
              style: const TextStyle(color: Tokens.dangerText)),
        ],
        const SizedBox(height: Tokens.space3),
        FilledButton(
          key: const Key('save-gateway'),
          onPressed: _busy ? null : _save,
          child: Text(_busy ? 'Saving…' : 'Save address'),
        ),
      ],
    );
  }
}
