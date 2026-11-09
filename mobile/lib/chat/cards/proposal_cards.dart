import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../api/api_error.dart';
import '../../theme/tokens.dart';
import '../../util/app_time.dart';
import 'approval_cards.dart' show askForText;
import 'card_base.dart';

Future<Json> _post(ApiClient api, String path, [Json? body]) async =>
    ((await api.post(path, body)) as Map).cast<String, dynamic>();

Future<Json> _get(ApiClient api, String path) async =>
    ((await api.get(path)) as Map).cast<String, dynamic>();

TextStyle get _small =>
    const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel);

/// A skill a bot offers (or a change to one). Only Save skill writes it.
class SkillProposalCard extends StatelessWidget {
  const SkillProposalCard({super.key, required this.body});
  final String body;

  @override
  Widget build(BuildContext context) {
    final id = str(decodeBody(body)?['proposal_id']);
    if (id.isEmpty) return QuietLine(body);
    final path = '/api/skill-proposals/$id';
    return FetchCard<Json>(
      key: ValueKey(id),
      refreshOn: const {'proposals_changed'},
      fetch: (api) => _get(api, path),
      gone: () => const QuietLine('This card is gone.'),
      builder: (context, ctx) {
        final p = ctx.item;
        if (p['state'] != 'open') {
          return QuietLine(p['state'] == 'saved' ? 'Skill saved' : 'Not saved');
        }
        final payload = (p['payload'] as Map?)?.cast<String, dynamic>() ?? {};
        final create = p['action'] == 'create';
        return CardFrame(
          title: create ? 'New skill' : 'Change a skill',
          badges: [
            if (p['tainted'] == true) 'from web content',
            if (p['from_routine'] == true) 'A routine proposed this',
          ],
          footer: [
            CardButton('Save skill',
                primary: true,
                onPressed:
                    ctx.busy ? null : () => ctx.act((a) => _post(a, '$path/save'))),
            CardButton('Not now',
                onPressed: ctx.busy
                    ? null
                    : () => ctx.act((a) => _post(a, '$path/decline'))),
          ],
          children: [
            if (create) ...[
              Text(str(payload['name']),
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              Text('Use when: ${str(payload['use_when'])}', style: _small),
              const SizedBox(height: Tokens.space1),
              Text(str(payload['body'])),
            ] else ...[
              Text(str(p['skill_name']),
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              for (final c in jsonList(p['diff'])) _Change(c),
            ],
            if (ctx.error != null) CardError(ctx.error!),
          ],
        );
      },
    );
  }
}

class _Change extends StatelessWidget {
  const _Change(this.change);
  final Json change;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: Tokens.space1),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(str(change['field']), style: _small),
            Text(str(change['before']),
                style: const TextStyle(
                    color: Tokens.danger,
                    decoration: TextDecoration.lineThrough)),
            Text(str(change['after']), style: const TextStyle(color: Tokens.ok)),
          ],
        ),
      );
}

/// "Update my instructions?": every changed line; only Accept writes them,
/// as offered or after Edit.
class InstructionsProposalCard extends StatelessWidget {
  const InstructionsProposalCard({super.key, required this.body});
  final String body;

  @override
  Widget build(BuildContext context) {
    final id = str(decodeBody(body)?['proposal_id']);
    if (id.isEmpty) return QuietLine(body);
    final path = '/api/instruction-proposals/$id';
    return FetchCard<Json>(
      key: ValueKey(id),
      refreshOn: const {'instruction_proposals_changed'},
      fetch: (api) => _get(api, path),
      gone: () => const QuietLine('This card is gone.'),
      builder: (context, ctx) {
        final p = ctx.item;
        if (p['state'] != 'open') {
          return QuietLine(
              p['state'] == 'accepted' ? 'Instructions updated' : 'Instructions kept');
        }
        final stale = p['stale'] == true;
        Future<void> edit() async {
          final text = await askForText(context,
              title: 'Your version',
              max: 4000,
              action: 'Accept',
              initial: str(p['after']));
          if (text != null && text.trim().isNotEmpty) {
            ctx.act((a) => _post(a, '$path/accept', {'text': text}));
          }
        }

        return CardFrame(
          title: 'Update my instructions?',
          badges: [
            if (p['tainted'] == true) 'from web content',
            if (p['from_routine'] == true) 'A routine proposed this',
          ],
          footer: [
            CardButton('Accept',
                primary: true,
                onPressed: ctx.busy || stale
                    ? null
                    : () => ctx.act((a) => _post(a, '$path/accept', {}))),
            CardButton('Edit', onPressed: ctx.busy || stale ? null : edit),
            CardButton('Decline',
                onPressed: ctx.busy
                    ? null
                    : () => ctx.act((a) => _post(a, '$path/decline'))),
          ],
          children: [
            if (str(p['why']).isNotEmpty) Text(str(p['why']), style: _small),
            for (final line in jsonList(p['diff']))
              Text(
                  '${line['op'] == 'add' ? '+ ' : line['op'] == 'del' ? '− ' : '  '}${str(line['text'])}',
                  style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: Tokens.fsCaption,
                      color: line['op'] == 'add'
                          ? Tokens.ok
                          : line['op'] == 'del'
                              ? Tokens.danger
                              : Tokens.textSecondary)),
            if (stale)
              const CardError(
                  "You changed this bot's instructions since this card was made, so it can't be accepted."),
            if (ctx.error != null) CardError(ctx.error!),
          ],
        );
      },
    );
  }
}

/// A routine a bot wants (or a change, or a pause), in full. Approve is what
/// makes the server write it.
class RoutineProposalCard extends StatelessWidget {
  const RoutineProposalCard({super.key, required this.body});
  final String body;

  static const _titles = {
    'create': 'New routine',
    'change': 'Change a routine',
    'pause': 'Pause a routine',
  };

  @override
  Widget build(BuildContext context) {
    final id = str(decodeBody(body)?['proposal_id']);
    if (id.isEmpty) return QuietLine(body);
    final path = '/api/routine-proposals/$id';
    return FetchCard<Json>(
      key: ValueKey(id),
      refreshOn: const {'proposals_changed'},
      fetch: (api) async {
        try {
          return ((await api.get(path)) as Map).cast<String, dynamic>();
        } on ApiException catch (e) {
          if (e.status == 404) return null;
          rethrow;
        }
      },
      gone: () => const QuietLine('Already decided'),
      builder: (context, ctx) {
        final p = ctx.item;
        final action = str(p['action'], 'create');
        return CardFrame(
          title: _titles[action] ?? 'Routine',
          badges: [
            if (p['from_routine'] == true) 'A routine asked to change a routine.',
            if (p['tainted'] == true) 'This run read outside content.',
          ],
          footer: [
            CardButton('Approve',
                primary: true,
                onPressed:
                    ctx.busy ? null : () => ctx.act((a) => _post(a, '$path/approve'))),
            CardButton('Decline',
                onPressed:
                    ctx.busy ? null : () => ctx.act((a) => _post(a, '$path/decline'))),
          ],
          children: [..._fields(p, action), if (ctx.error != null) CardError(ctx.error!)],
        );
      },
    );
  }

  List<Widget> _fields(Json p, String action) {
    final payload = (p['payload'] as Map?)?.cast<String, dynamic>();
    if (action == 'pause') return [Text(str(p['routine_name'], 'This routine'))];
    if (action == 'change') {
      return [
        Text(str(p['routine_name']),
            style: const TextStyle(fontWeight: FontWeight.w600)),
        for (final c in jsonList(p['diff'])) _Change(c),
      ];
    }
    final next = [for (final t in (p['next'] as List? ?? const [])) str(t)];
    return [
      Text(str(payload?['name']),
          style: const TextStyle(fontWeight: FontWeight.w600)),
      Text(str(p['words']), style: _small),
      for (final t in next.take(3)) Text(appDayClock(t), style: _small),
      Text(str(payload?['instructions'])),
    ];
  }
}
