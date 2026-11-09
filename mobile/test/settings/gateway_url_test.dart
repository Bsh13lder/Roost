import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/gateway_url.dart';

void main() {
  test('plain http is allowed only for this phone (127.0.0.1, localhost)', () {
    expect(checkGatewayUrl('http://127.0.0.1:18800/').url,
        'http://127.0.0.1:18800');
    expect(checkGatewayUrl('http://localhost:18800').url,
        'http://localhost:18800');
    expect(checkGatewayUrl('127.0.0.1:18800').url, 'http://127.0.0.1:18800');
  });

  test('any other address must be https', () {
    expect(checkGatewayUrl('https://mac.tail1234.ts.net').url,
        'https://mac.tail1234.ts.net');
    expect(checkGatewayUrl('mac.tail1234.ts.net').url,
        'https://mac.tail1234.ts.net');
    final refused = checkGatewayUrl('http://mac.tail1234.ts.net');
    expect(refused.url, isNull);
    expect(refused.error, contains('https'));
  });

  test('nonsense is refused with a friendly sentence', () {
    for (final bad in ['', '   ', 'ftp://x.ts.net', 'https://', 'https://a b']) {
      final r = checkGatewayUrl(bad);
      expect(r.url, isNull, reason: bad);
      expect(r.error, isNotEmpty, reason: bad);
    }
  });

  test('a path or query is refused', () {
    expect(checkGatewayUrl('https://mac.ts.net/api?x=1').url, isNull);
  });
}
