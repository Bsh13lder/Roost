/// Hosts that are this phone itself (reached over `adb reverse`), the only
/// ones plain http may go to. Everything else (the Mac's Tailscale address)
/// must be https.
const localGatewayHosts = {'127.0.0.1', 'localhost'};

/// The outcome of [checkGatewayUrl]: a clean address, or a sentence why not.
class GatewayCheck {
  const GatewayCheck.ok(String this.url) : error = null;
  const GatewayCheck.refused(String this.error) : url = null;

  final String? url;
  final String? error;
}

const _badAddress = 'That gateway address is not valid.';
const _needsHttps =
    'Use https for any address that is not this phone (127.0.0.1 or localhost).';

/// Reads a typed gateway address. A missing scheme means http for this
/// phone and https for anything else; a path, a query or another scheme is
/// refused.
GatewayCheck checkGatewayUrl(String raw) {
  var text = raw.trim();
  if (text.isEmpty || text.contains(' ')) {
    return const GatewayCheck.refused(_badAddress);
  }
  if (!text.contains('://')) {
    final host = text.split(RegExp('[:/]')).first.toLowerCase();
    final scheme = localGatewayHosts.contains(host) ? 'http' : 'https';
    text = '$scheme://$text';
  }
  while (text.endsWith('/')) {
    text = text.substring(0, text.length - 1);
  }
  final uri = Uri.tryParse(text);
  if (uri == null || uri.host.isEmpty) {
    return const GatewayCheck.refused(_badAddress);
  }
  return _checkParts(uri);
}

GatewayCheck _checkParts(Uri uri) {
  if (uri.path.isNotEmpty || uri.hasQuery || uri.hasFragment) {
    return const GatewayCheck.refused(_badAddress);
  }
  final host = uri.host.toLowerCase();
  if (uri.scheme == 'http') {
    return localGatewayHosts.contains(host)
        ? GatewayCheck.ok(_origin(uri))
        : const GatewayCheck.refused(_needsHttps);
  }
  if (uri.scheme == 'https') return GatewayCheck.ok(_origin(uri));
  return const GatewayCheck.refused(_badAddress);
}

String _origin(Uri uri) =>
    '${uri.scheme}://${uri.host.toLowerCase()}${uri.hasPort ? ':${uri.port}' : ''}';
