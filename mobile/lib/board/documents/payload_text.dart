// Reads a Univer snapshot into plain text or a grid, for the read-only view.
// Anything it cannot read comes back empty rather than throwing.

/// A doc's text: its `body.dataStream`, paragraphs split on `\r`.
String docText(Map<String, dynamic>? payload) {
  final body = payload?['body'];
  final stream = body is Map ? body['dataStream'] : null;
  if (stream is! String) return '';
  return stream
      .replaceAll('\r\n', '')
      .split('\r')
      .map((p) => p.replaceAll(RegExp(r'[\u0000-\u0008\u000b-\u001f]'), ''))
      .join('\n')
      .trimRight();
}

class SheetGrid {
  const SheetGrid(this.name, this.rows);

  final String name;
  final List<List<String>> rows;
}

/// The sheets of a workbook in `sheetOrder`, each trimmed to its used cells.
List<SheetGrid> sheetGrids(Map<String, dynamic>? payload) {
  final sheets = payload?['sheets'];
  if (sheets is! Map) return const [];
  final order = payload?['sheetOrder'];
  final ids = order is List ? order.map((e) => '$e').toList() : sheets.keys.map((e) => '$e').toList();
  final grids = <SheetGrid>[];
  for (final id in ids) {
    final sheet = sheets[id];
    if (sheet is! Map) continue;
    final cells = sheet['cellData'];
    var maxRow = -1;
    var maxCol = -1;
    final values = <(int, int), String>{};
    if (cells is Map) {
      cells.forEach((r, row) {
        final ri = int.tryParse('$r');
        if (ri == null || row is! Map) return;
        row.forEach((c, cell) {
          final ci = int.tryParse('$c');
          final v = cell is Map ? cell['v'] : null;
          if (ci == null || v == null || '$v'.isEmpty) return;
          values[(ri, ci)] = '$v';
          if (ri > maxRow) maxRow = ri;
          if (ci > maxCol) maxCol = ci;
        });
      });
    }
    grids.add(SheetGrid('${sheet['name'] ?? 'Sheet'}', [
      for (var r = 0; r <= maxRow; r++)
        [for (var c = 0; c <= maxCol; c++) values[(r, c)] ?? ''],
    ]));
  }
  return grids;
}
