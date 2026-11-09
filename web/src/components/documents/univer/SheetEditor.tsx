import { sheetKit } from "./sheetKit";
import { UniverEditor } from "./UniverEditor";
import type { DocumentDetailOut } from "../../../api/types";

// Its own lazy chunk (D4): the Univer sheets engine loads only when a sheet opens.
export default function SheetEditor({ document }: { document: DocumentDetailOut }) {
  return <UniverEditor kit={sheetKit} document={document} />;
}
