// The quick line's tokens for the "?" help, copied from the web's
// quickHelpTokens.ts. Every example is read by the server's grammar.

class HelpToken {
  const HelpToken(this.token, this.en, this.es, this.means);

  final String token;
  final String en;
  final String es;
  final String means;
}

const taskTokens = [
  HelpToken('tomorrow at 9', 'Call Ana tomorrow at 9', 'Llamar a Ana mañana a las 9',
      'Due date and time'),
  HelpToken('tmrw · mon', 'Call Ana tmrw', 'Llamar a Ana mnn',
      'Short days and words: tom, tmr, tmrw, tod, nxt wk, mon to sun, lun to dom'),
  HelpToken('!!', 'Pay rent !!', 'Pagar el alquiler !!',
      'Priority: !!! urgent, !! high, ! medium, !- low (also !urgent, !alta, !baja)'),
  HelpToken('p1', 'Pay rent p1', 'Pagar el alquiler p1',
      'Priority the Todoist way: p1 urgent, p2 high, p3 medium, p4 low'),
  HelpToken("'", "'Call Ana tomorrow !!", "'Llamar a Ana mañana !!",
      "A leading ' (or the whole line in quotes) adds it exactly as typed"),
  HelpToken('*', 'Send invoice *', 'Enviar la factura *', 'Star it'),
  HelpToken('~1h30', 'Paint wall ~2h', 'Pintar la pared ~1,5h', 'How long it takes'),
  HelpToken('^9am', 'Call Ana ^1h before', 'Llamar a Ana ^30m antes',
      'Remind you at a time, or before the due date'),
  HelpToken('every Monday', 'Water plants every Monday', 'Regar las plantas cada lunes',
      'Repeat: daily, weekdays, weekly, monthly, yearly'),
  HelpToken('every other', 'Gym every other Monday', 'Gimnasio cada otro lunes',
      'Every other day, week or month, or every 3 days / 2 weeks / 2 months'),
  HelpToken('starting · ending', 'Course every 2 weeks starting Nov 3 ending Dec 15',
      'Curso cada 2 semanas empezando el 3 nov hasta el 15 dic',
      'When a repeat begins and its last day'),
  HelpToken('every!', 'Water plants every! 3 days', 'Regar cada! 3 días',
      'Repeat from when you finish it (also: when done)'),
  HelpToken('Date · Project · Priority · Repeat · Remind', 'Buttons above the line',
      'Botones sobre la línea',
      'Pick instead of typing: each button writes the same words into the line'),
  HelpToken('@Scout', 'Book flights @Scout', 'Reservar vuelos @Scout',
      'Hand it to a bot (you confirm first)'),
  HelpToken('/Renovation', 'Order tiles /Renovation', 'Pedir azulejos /Reforma',
      'Put it in a project that exists (longest name wins; a near miss asks)'),
  HelpToken('#tag', 'Buy milk #shopping', 'Comprar leche #compras',
      'Add a tag; # never picks a project'),
  HelpToken('€200', 'Plumber €200 /Renovation', 'Fontanero 200€ /Reforma',
      "Its budget, in the project's money (General's with no project)"),
  HelpToken('€3x45', 'Paint walls /Renovation €3x45', 'Pintar paredes /Reforma 3x45€',
      'Sums work in any amount: x, + and / (up to 6 numbers)'),
];
