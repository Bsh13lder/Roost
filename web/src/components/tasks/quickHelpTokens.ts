// The quick lines' tokens, for the "?" help (Tasks & Money polish). One table per line, each row with a
// token, an English and a Spanish example, and what it means. Every example is read by the server's
// grammar (roost/tasks/line_tokens.py, repeat_words.py, day_words.py).
export interface HelpToken {
  token: string;
  en: string;
  es: string;
  means: string;
}

export const TASK_TOKENS: readonly HelpToken[] = [
  { token: "tomorrow at 9", en: "Call Ana tomorrow at 9", es: "Llamar a Ana mañana a las 9", means: "Due date and time" },
  { token: "tmrw · mon", en: "Call Ana tmrw", es: "Llamar a Ana mnn",
    means: "Short days and words: tom, tmr, tmrw, tod, nxt wk, mon to sun, lun to dom (mar only in a Spanish line or before a time)" },
  { token: "!!", en: "Pay rent !!", es: "Pagar el alquiler !!",
    means: "Priority: !!! urgent, !! high, ! medium, !- low (also !urgent, !alta, !baja)" },
  { token: "p1", en: "Pay rent p1", es: "Pagar el alquiler p1",
    means: "Priority the Todoist way: p1 urgent, p2 high, p3 medium, p4 low (also priority 1)" },
  { token: "'", en: "'Call Ana tomorrow !!", es: "'Llamar a Ana mañana !!",
    means: "A leading ' (or the whole line in quotes) adds it exactly as typed" },
  { token: "*", en: "Send invoice *", es: "Enviar la factura *", means: "Star it" },
  { token: "~1h30", en: "Paint wall ~2h", es: "Pintar la pared ~1,5h", means: "How long it takes" },
  { token: "^9am", en: "Call Ana ^1h before", es: "Llamar a Ana ^30m antes",
    means: "Remind you at a time, or before the due date" },
  { token: "every Monday", en: "Water plants every Monday", es: "Regar las plantas cada lunes",
    means: "Repeat: daily, weekdays, weekly, monthly, yearly" },
  { token: "every other", en: "Gym every other Monday", es: "Gimnasio cada otro lunes",
    means: "Every other day, week or month, or every 3 days / 2 weeks / 2 months" },
  { token: "starting · ending", en: "Course every 2 weeks starting Nov 3 ending Dec 15",
    es: "Curso cada 2 semanas empezando el 3 nov hasta el 15 dic",
    means: "When a repeat begins and its last day" },
  { token: "every!", en: "Water plants every! 3 days", es: "Regar cada! 3 días",
    means: "Repeat from when you finish it (also: when done)" },
  { token: "Paste a list", en: "One task per line, indent for steps", es: "Una tarea por línea, sangra para los pasos",
    means: "Pasting several lines asks “Add N tasks?” first" },
  { token: "Date · Project · Priority · Tag · Repeat", en: "Buttons under the line", es: "Botones bajo la línea",
    means: "Pick instead of typing: each button writes the same words into the line" },
  { token: "@Scout", en: "Book flights @Scout", es: "Reservar vuelos @Scout",
    means: "Hand it to a bot (you confirm first)" },
  { token: "/Renovation", en: "Order tiles /Renovation", es: "Pedir azulejos /Reforma",
    means: "Put it in a project that exists (longest name wins; a near miss asks)" },
  { token: "#tag", en: "Buy milk #shopping", es: "Comprar leche #compras",
    means: "Add a tag; # never picks a project" },
  { token: "€200", en: "Plumber €200 /Renovation", es: "Fontanero 200€ /Reforma",
    means: "Its budget, in the project's money (General's with no project)" },
  { token: "€3x45", en: "Paint walls /Renovation €3x45", es: "Pintar paredes /Reforma 3x45€",
    means: "Sums work in any amount: x, + and / (up to 6 numbers), shown as €135.00 = 3×45" },
];

export const EXPENSE_TOKENS: readonly HelpToken[] = [
  { token: "€12", en: "€12 lunch", es: "12,50€ comida", means: "The amount; its sign sets the money" },
  { token: "€2x31", en: "€2x31 paint", es: "2x31€ pintura",
    means: "Sums work in any amount: x, + and / (up to 6 numbers), shown as €62.00 = 2×31" },
  { token: "+€500", en: "+€500 salary", es: "+500€ nómina", means: "Money in: kept apart, never counted as spent" },
  { token: "/Trip", en: "€12 lunch /Trip", es: "12€ comida /Viaje", means: "The project, if it exists" },
  { token: "yesterday", en: "€12 coffee yesterday", es: "12€ café ayer", means: "A day in the past" },
  { token: "vendor:", en: "€12 lunch vendor:Mercadona", es: "12€ comida tienda:Mercadona",
    means: "Where you paid; quote names with spaces" },
  { token: "*", en: "€12 lunch *", es: "12€ comida *", means: "Star it" },
  { token: "monthly", en: "€9.99 Netflix /Home monthly", es: "9,99€ Netflix /Casa cada mes",
    means: "Makes it a repeating expense" },
];
