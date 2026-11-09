// Fake demo data for scripts/readme-shots.mjs: a small café, "Café Lumen". Every name is made up.
// Task rows: [title, due offset in days or null, priority, project index or null, steps, steps done, budget slice].
// Expense rows: [day offset, amount, note, project index or null].

export const BOTS = [
  { name: "Shop helper", job: "Orders supplies for the café on our shop sites", shape: "bun", color: "#f97316", role: "general" },
  { name: "Bookkeeper", job: "Logs expenses and checks supplier invoices", shape: "loaf", color: "#22c55e", role: "money" },
  { name: "Social media", job: "Plans the café's Instagram posts", shape: "gumdrop", color: "#ec4899", role: "social" },
];

export const PROJECTS = [
  { name: "Café Lumen", currency: "EUR", budget: null, monthly_budget: "3000", color: "#f97316" },
  { name: "Summer terrace", currency: "EUR", budget: "4500", monthly_budget: null, color: "#3b82f6" },
  { name: "Instagram", currency: "EUR", budget: null, monthly_budget: "300", color: "#ec4899" },
];

export const TASKS = [
  ["Order coffee beans (12 kg)", 0, "high", 0, ["Check what's left", "Email the roaster", "Confirm delivery day"], 1, "240"],
  ["Pay supplier invoices", -1, "urgent", 0, ["Dairy", "Bakery", "Cleaning products"], 1, "412"],
  ["Staff schedule for next week", 2, "medium", 0, ["Ask who wants extra hours", "Post it in the back room"], 0, null],
  ["Deep-clean the grinder", 4, "low", 0, [], 0, null],
  ["Health inspection papers", 9, "high", 0, ["Find the fridge logs", "Print the allergen list"], 1, null],
  ["Get quotes for terrace awnings", 1, "medium", 1, ["Ask two installers", "Compare prices"], 1, "1800"],
  ["Buy 6 outdoor tables", 6, "medium", 1, [], 0, "1200"],
  ["Apply for the terrace permit", -3, "urgent", 1, ["Fill in the form", "Pay the fee"], 1, "150"],
  ["Post the pumpkin latte", 0, "medium", 2, ["Take the photo", "Write the caption"], 1, null],
  ["Plan November posts", 3, "low", 2, ["Pick 8 photos", "Draft captions", "Schedule them"], 0, null],
  ["Boost the weekend brunch post", 5, "low", 2, [], 0, "40"],
  ["Renew the card terminal contract", 12, "medium", null, [], 0, null],
  ["Fix the wobbly bar stool", null, "low", null, [], 0, null],
  ["New loyalty cards", null, "medium", null, [], 0, null],
];

export const EXPENSES = [
  [0, "238.50", "Coffee beans, 12 kg", 0], [0, "86.40", "Dairy invoice", 0], [-1, "64.20", "Bakery delivery", 0],
  [-1, "18.90", "Cleaning products", 0], [-2, "120", "Awning quote deposit", 1], [-2, "29", "Instagram ad", 2],
  [-3, "150", "Terrace permit fee", 1], [-3, "42.75", "Paper cups and lids", 0], [-4, "312", "Staff lunch & tips", 0],
  [-4, "15", "Photo props", 2], [-5, "96.80", "Fresh fruit", 0], [-6, "54.30", "Oat milk, 2 crates", 0],
  [-7, "210", "Espresso machine service", 0], [-8, "35", "Canva plan", 2], [-9, "71.60", "Bakery delivery", 0],
  [-10, "480", "Outdoor tables deposit", 1], [-11, "24.90", "Napkins", 0], [-12, "88.40", "Dairy invoice", 0],
];

// One routine per bot that has one, run times in Madrid (1 = Monday).
export const ROUTINES = [
  { bot: "Bookkeeper", name: "Morning orders check", schedule: { kind: "times", days: [1, 2, 3, 4, 5, 6], times: ["08:00"] },
    instructions: "Check yesterday's orders and supplier invoices, and tell me anything that needs paying today." },
  { bot: "Social media", name: "Weekly post ideas", schedule: { kind: "times", days: [1], times: ["10:00"] },
    instructions: "Suggest three Instagram posts for this week from the café's specials." },
  { bot: "Chief", name: "Friday staff schedule", schedule: { kind: "times", days: [5], times: ["17:00"] },
    instructions: "Draft next week's staff schedule from the open tasks and remind me to post it." },
];

export const MESSAGES = {
  chief: "We're nearly out of oat milk and the espresso machine is dripping again. Add both to my tasks and tell me what's on this week.",
  social: "Give me three Instagram ideas for the new pumpkin latte.",
  shop: "Please order one blue mug for the counter from shop.test.",
};
