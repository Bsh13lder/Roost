import { useEffect, useState } from "react";
import * as templatesApi from "../api/templates";
import { describeError } from "../api/client";
import type { TemplateOut } from "../api/types";

// The "Start from" templates (S1.7); a failed load is said, never swallowed.
export function useTemplates() {
  const [templates, setTemplates] = useState<TemplateOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    templatesApi.listTemplates()
      .then((loaded) => { if (live) setTemplates(loaded); })
      .catch((err: unknown) => { if (live) setError(describeError(err)); });
    return () => { live = false; };
  }, []);
  return { templates, error };
}
