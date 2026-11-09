import { docKit } from "./docKit";
import { UniverEditor } from "./UniverEditor";
import type { DocumentDetailOut } from "../../../api/types";

// Its own lazy chunk (D4): the Univer docs engine loads only when a doc opens.
export default function DocEditor({ document }: { document: DocumentDetailOut }) {
  return <UniverEditor kit={docKit} document={document} />;
}
