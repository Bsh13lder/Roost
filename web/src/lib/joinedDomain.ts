// A sentence that ends in a domain and runs straight into the next word ("opening www.upwork.com.done: ...")
// is autolinked as one host. A host whose generic TLD (com, org, ...) is followed by a label that is not a
// country code or a second-level label (com.au, co.uk) is that domain plus a glued-on word: split it there.
const GENERIC_TLDS = new Set(["com", "org", "net", "io", "dev", "app", "ai", "edu", "gov", "info", "biz"]);
const SECOND_LEVEL = new Set(["com", "org", "net", "co", "gov", "edu", "ac"]);

export interface HostSplit {
  readonly host: string;
  readonly rest: string;
}

function belongsToHost(label: string): boolean {
  return label.length === 2 || SECOND_LEVEL.has(label);
}

export function splitJoinedDomain(host: string): HostSplit {
  const labels = host.split(".");
  for (let i = 1; i < labels.length - 1; i += 1) {
    if (GENERIC_TLDS.has(labels[i].toLowerCase()) && !belongsToHost(labels[i + 1].toLowerCase())) {
      return { host: labels.slice(0, i + 1).join("."), rest: `.${labels.slice(i + 1).join(".")}` };
    }
  }
  return { host, rest: "" };
}
