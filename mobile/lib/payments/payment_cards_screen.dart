import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../chat/cards/pay_card.dart' show savedCardLabel;
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';

typedef Json = Map<String, dynamic>;

/// Vault: cards (owner, 2026-11-05), from Settings: the cards you saved from a Pay card, as brand and last 4 only.
/// Roost never keeps the security code, so a Pay card always asks for it. Delete removes a card at once.
class PaymentCardsScreen extends ConsumerWidget {
  const PaymentCardsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('Vault: cards')),
    body: SingleChildScrollView(
      padding: const EdgeInsets.all(Tokens.space4),
      child: LoadView<List<Json>>(
        load: () async {
          final data =
              await ref.read(apiClientProvider).get('/api/payment-cards')
                  as List;
          return [for (final c in data) (c as Map).cast<String, dynamic>()];
        },
        builder: (context, cards, reload) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (cards.isEmpty)
              const Quiet(
                'No saved cards. Tick Save this card on a Pay card to keep one.',
              ),
            for (final c in cards)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(savedCardLabel(c)),
                trailing: TextButton(
                  key: Key('delete-card-${c['id']}'),
                  onPressed: () async {
                    await ref
                        .read(apiClientProvider)
                        .delete('/api/payment-cards/${c['id']}');
                    await reload();
                  },
                  child: const Text('Delete'),
                ),
              ),
            const Quiet(
              'Saved cards are encrypted. The security code is never kept.',
            ),
          ],
        ),
      ),
    ),
  );
}
