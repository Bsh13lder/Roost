import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../api/providers.dart';
import '../../theme/tokens.dart';

class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key});

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _url = TextEditingController();
  final _user = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _showPassword = false;   // lets you check what the phone's keyboard typed
  bool _urlSeeded = false;
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _user.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_user.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = 'Enter your username and password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(authProvider.notifier)
          .signIn(_url.text, _user.text.trim(), _password.text);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } on FormatException {
      if (mounted) setState(() => _error = 'That gateway address is not valid.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    if (!_urlSeeded && auth.ready) {
      _url.text = auth.baseUrl;
      _urlSeeded = true;
    }
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Tokens.space6),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: _form(),
            ),
          ),
        ),
      ),
    );
  }

  Widget _form() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'Roost',
          style: TextStyle(
            fontSize: Tokens.fsDisplay,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: Tokens.space1),
        const Text(
          'Sign in to your gateway.',
          style: TextStyle(color: Tokens.textSecondary),
        ),
        const SizedBox(height: Tokens.space6),
        TextField(
          key: const Key('gateway-url'),
          controller: _url,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(labelText: 'Gateway address'),
        ),
        const SizedBox(height: Tokens.space3),
        TextField(
          key: const Key('username'),
          controller: _user,
          autocorrect: false,
          enableSuggestions: false,
          textCapitalization: TextCapitalization.none,
          decoration: const InputDecoration(labelText: 'Username'),
        ),
        const SizedBox(height: Tokens.space3),
        TextField(
          key: const Key('password'),
          controller: _password,
          obscureText: !_showPassword,
          autocorrect: false,
          enableSuggestions: false,
          keyboardType: TextInputType.visiblePassword,
          onSubmitted: (_) => _submit(),
          decoration: InputDecoration(
            labelText: 'Password',
            suffixIcon: IconButton(
              key: const Key('show-password'),
              tooltip: _showPassword ? 'Hide password' : 'Show password',
              icon: Icon(_showPassword ? Icons.visibility_off : Icons.visibility),
              onPressed: () => setState(() => _showPassword = !_showPassword),
            ),
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: Tokens.space3),
          Text(_error!, style: const TextStyle(color: Tokens.dangerText)),
        ],
        const SizedBox(height: Tokens.space5),
        FilledButton(
          key: const Key('sign-in'),
          onPressed: _busy ? null : _submit,
          child: Text(_busy ? 'Signing in…' : 'Sign in'),
        ),
      ],
    );
  }
}
